"""
Claude Runner Module

Handles the execution of Claude CLI for batch processing.

Includes:
  - Async execution with semaphore-based concurrency control
  - Automatic retry on transient failures with exponential backoff
  - **Circuit breaker** that halts execution after consecutive failures
  - **Log anomaly detection** to catch runaway retry loops early
  - **Real-time log watcher** that monitors logs during execution
  - **Cost tracking** with per-batch token usage extraction
  - Structured logging and result parsing
"""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import aiofiles

from .config import PhaseConfig
from .watchdog import (
    LogWatcher,
    LogWatcherConfig,
    CostTracker,
    BudgetExceeded,
    extract_token_usage_from_log,
)


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitBreakerTripped(Exception):
    """Raised when the circuit breaker threshold is exceeded."""

    def __init__(self, reason: str, stats: dict[str, int]):
        self.reason = reason
        self.stats = stats
        super().__init__(f"Circuit breaker tripped: {reason} (stats={stats})")


class CircuitBreaker:
    """
    Tracks failure / anomaly counters and raises ``CircuitBreakerTripped``
    when configurable thresholds are exceeded.

    Counters are **shared** across all workers within a single phase run,
    which means a systemic issue (e.g. bad prompt, API outage) is detected
    quickly even when many batches are in flight.
    """

    def __init__(self, config: PhaseConfig):
        self.config = config

        # Counters (all thread-safe via GIL for simple int increments)
        self.consecutive_failures: int = 0
        self.total_retries: int = 0
        self.empty_results: int = 0
        self.total_successes: int = 0
        self.total_failures: int = 0

        # Lock for compound check-and-update
        self._lock = asyncio.Lock()

    async def record_success(self) -> None:
        """Record a successful batch execution."""
        async with self._lock:
            self.consecutive_failures = 0
            self.total_successes += 1

    async def record_failure(self) -> None:
        """Record a batch failure and check thresholds."""
        async with self._lock:
            self.consecutive_failures += 1
            self.total_failures += 1
            self._check_thresholds()

    async def record_retry(self) -> None:
        """Record a retry attempt and check thresholds."""
        async with self._lock:
            self.total_retries += 1
            self._check_thresholds()

    async def record_empty_result(self) -> None:
        """Record a batch that returned an empty result set."""
        async with self._lock:
            self.empty_results += 1
            self._check_thresholds()

    def _check_thresholds(self) -> None:
        """Raise if any threshold is exceeded.  Called under lock."""
        stats = self.get_stats()

        if self.consecutive_failures >= self.config.circuit_breaker_threshold:
            raise CircuitBreakerTripped(
                f"{self.consecutive_failures} consecutive failures "
                f"(threshold={self.config.circuit_breaker_threshold})",
                stats,
            )

        if self.total_retries >= self.config.max_total_retries:
            raise CircuitBreakerTripped(
                f"{self.total_retries} total retries "
                f"(threshold={self.config.max_total_retries})",
                stats,
            )

        if self.empty_results >= self.config.max_empty_results:
            raise CircuitBreakerTripped(
                f"{self.empty_results} empty-result batches "
                f"(threshold={self.config.max_empty_results})",
                stats,
            )

    def get_stats(self) -> dict[str, int]:
        """Return a snapshot of all counters."""
        return {
            "consecutive_failures": self.consecutive_failures,
            "total_retries": self.total_retries,
            "empty_results": self.empty_results,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
        }


# ---------------------------------------------------------------------------
# Log Anomaly Detector (static / post-hoc — kept for backward compat)
# ---------------------------------------------------------------------------

class LogAnomalyDetector:
    """
    Lightweight heuristic scanner for Claude CLI stream-json logs.

    Detects patterns that indicate the LLM is stuck in a retry loop,
    producing garbage output, or otherwise behaving anomalously.

    **Important**: This scanner parses each log line as JSON and only
    inspects structural/error fields — NOT user content embedded in
    ``tool_result`` or ``text`` blocks — to avoid false positives from
    domain-specific terms like "429", "rate limit", "timeout" etc.

    Note: For real-time monitoring during execution, use ``LogWatcher``
    from the ``watchdog`` module instead.
    """

    # Patterns applied to extracted error text only
    _ANOMALY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
        ("rate_limit_error", re.compile(r"rate.?limit|429|too many requests", re.IGNORECASE)),
        ("context_overflow", re.compile(r"context.?length|token.?limit|maximum.?context", re.IGNORECASE)),
        ("api_error", re.compile(r"APIError|InternalServerError|ServiceUnavailable|overloaded", re.IGNORECASE)),
        ("timeout_error", re.compile(r"timed?\s*out|deadline exceeded|ETIMEDOUT", re.IGNORECASE)),
        ("usage_limit", re.compile(r"out of (?:extra )?usage|usage.?limit|resets? \w+ \d+", re.IGNORECASE)),
    ]

    # Fatal patterns that indicate systemic issues (no point retrying)
    _FATAL_PATTERNS: frozenset[str] = frozenset({"usage_limit"})

    # If the log contains more than this many tool_use blocks it's likely looping.
    # Phase 03 batches of 25 items each require multiple tool calls, so 50 is
    # too low and causes false positives.  200 is a safer default.
    TOOL_CALL_THRESHOLD = 200

    @classmethod
    def scan_log(cls, log_path: Path | str) -> list[str]:
        """
        Scan a log file and return a list of anomaly descriptions.

        Parses each line as JSON and only inspects error/system fields
        to avoid false positives from user content.

        Returns an empty list if no anomalies are found.
        """
        from .watchdog import _extract_scannable_text

        if not isinstance(log_path, Path):
            log_path = Path(log_path)
        if not log_path.exists():
            return []

        anomalies: list[str] = []
        tool_call_count = 0

        try:
            with open(log_path, errors="replace") as f:
                for line in f:
                    text_to_scan, is_tool_use = _extract_scannable_text(line)

                    if is_tool_use:
                        tool_call_count += 1

                    if text_to_scan:
                        for name, pattern in cls._ANOMALY_PATTERNS:
                            if pattern.search(text_to_scan):
                                anomalies.append(f"{name}: {text_to_scan.strip()[:200]}")
        except Exception:
            pass

        if tool_call_count > cls.TOOL_CALL_THRESHOLD:
            anomalies.append(
                f"excessive_tool_calls: {tool_call_count} tool_use blocks "
                f"(threshold={cls.TOOL_CALL_THRESHOLD})"
            )

        return anomalies

    @classmethod
    def has_fatal_anomaly(cls, anomalies: list[str]) -> bool:
        """
        Check if any anomaly in the list is a fatal pattern.

        Fatal anomalies (e.g. usage_limit) indicate systemic issues that
        cannot be resolved by retrying.  The caller should immediately
        trip the circuit breaker.
        """
        for desc in anomalies:
            for fatal_name in cls._FATAL_PATTERNS:
                if desc.startswith(f"{fatal_name}:"):
                    return True
        return False


# ---------------------------------------------------------------------------
# Claude Runner
# ---------------------------------------------------------------------------

class ClaudeRunner:
    """
    Executes Claude CLI commands for batch processing.

    Features:
    - Async execution with semaphore-based concurrency control
    - Automatic retry on transient failures
    - **Circuit breaker** integration (shared across workers)
    - **Real-time log watcher** during each batch execution
    - **Cost tracking** with token usage extraction from logs
    - **Log anomaly detection** after each batch (post-hoc)
    - Structured logging
    - Result parsing
    """

    def __init__(
        self,
        config: PhaseConfig,
        semaphore: asyncio.Semaphore,
        max_retries: int = 2,
        circuit_breaker: CircuitBreaker | None = None,
        cost_tracker: CostTracker | None = None,
    ):
        self.config = config
        self.semaphore = semaphore
        self.max_retries = max_retries
        self.circuit_breaker = circuit_breaker or CircuitBreaker(config)
        self.cost_tracker = cost_tracker

        # Ensure directories exist
        self.output_dir = Path("outputs")
        self.log_dir = self.output_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        Path(".claude/debug").mkdir(parents=True, exist_ok=True)

    async def run_batch(
        self,
        batch: list[dict[str, Any]],
        worker_id: int,
        batch_index: int,
    ) -> list[dict[str, Any]] | None:
        """
        Execute Claude CLI for a batch of items.

        Returns:
            List of results on success, None on failure.

        Raises:
            CircuitBreakerTripped: when failure thresholds are exceeded.
            BudgetExceeded: when cumulative cost exceeds the budget.
        """
        async with self.semaphore:
            for attempt in range(self.max_retries + 1):
                try:
                    result = await self._execute_batch(batch, worker_id, batch_index)
                    if result is not None:
                        if len(result) == 0:
                            # LLM returned valid JSON but no useful items
                            await self.circuit_breaker.record_empty_result()
                            print(
                                f"[W{worker_id}] Batch {batch_index}: empty result set",
                                file=sys.stderr,
                            )
                        else:
                            await self.circuit_breaker.record_success()
                        return result
                except (CircuitBreakerTripped, BudgetExceeded):
                    raise  # Propagate immediately
                except Exception as e:
                    print(
                        f"[W{worker_id}] Batch {batch_index} attempt {attempt + 1} failed: {e}",
                        file=sys.stderr,
                    )

                # Record retry (except on last attempt which becomes a failure)
                if attempt < self.max_retries:
                    await self.circuit_breaker.record_retry()
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

            # All retries exhausted
            await self.circuit_breaker.record_failure()
            return None

    async def _execute_batch(
        self,
        batch: list[dict[str, Any]],
        worker_id: int,
        batch_index: int,
    ) -> list[dict[str, Any]] | None:
        """Internal method to execute a single batch."""
        timestamp = int(time.time())
        phase_id = self.config.phase_id
        directory_mode = self.config.output_mode == "directory"

        # Create queue file
        # Always use simple {phase_id}_PARTIAL_* naming - no prefix needed
        partial_base = f"{phase_id}_PARTIAL"
        queue_path = self.output_dir / f"{phase_id}_ASYNC_QUEUE_W{worker_id}B{batch_index}_{timestamp}.json"
        log_file = self.log_dir / f"{phase_id}_w{worker_id}b{batch_index}_{timestamp}.log.jsonl"

        # Determine output paths based on output_mode
        if directory_mode:
            batch_output_dir = self.output_dir / "graphs" / f"batch_w{worker_id}b{batch_index}_{timestamp}"
            batch_output_dir.mkdir(parents=True, exist_ok=True)
            # Directory mode has no result file; _parse_results will return []
            # and the runner falls back to _parse_results_from_log automatically.
            result_parse_path = batch_output_dir / ".no_result_file"
            output_kwargs: dict[str, str] = {"output_dir": str(batch_output_dir)}
        else:
            result_parse_path = self.output_dir / f"{partial_base}_W{worker_id}B{batch_index}_{timestamp}.json"
            output_kwargs = {"output_file": str(result_parse_path)}

        # Save queue (ID-only) and context (full item data, optionally filtered)
        context_path = self.output_dir / f"{phase_id}_CONTEXT_W{worker_id}B{batch_index}_{timestamp}.json"
        queue_payload = self._build_queue_payload(batch, worker_id, str(context_path))
        context_payload = self._build_context_payload(batch)
        self._save_json(queue_path, queue_payload)
        self._save_json(context_path, context_payload)

        # Build prompt
        prompt_content = self._build_prompt(
            worker_id=worker_id,
            queue_file=str(queue_path),
            context_file=str(context_path),
            batch_size=len(batch),
            iteration=batch_index,
            timestamp=timestamp,
            **output_kwargs,
        )

        # Build command
        cmd = self._build_cmd(prompt_content)

        # Build environment
        env = self._build_env(
            worker_id=worker_id,
            queue_file=str(queue_path),
            context_file=str(context_path),
            batch_size=len(batch),
            iteration=batch_index,
            timestamp=timestamp,
            **output_kwargs,
        )

        # --- Start real-time log watcher ---
        watcher_config = LogWatcherConfig(
            anomaly_threshold=self.config.log_anomaly_threshold,
        )
        watcher = LogWatcher(log_file, config=watcher_config)
        watcher_task = asyncio.create_task(watcher.watch())

        # Execute
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=self.config.workdir or str(Path.cwd()),
        )

        # Collect stderr concurrently so it's available for error logging.
        # Reading stdout and stderr sequentially risks deadlock when the
        # subprocess writes enough to fill the OS pipe buffer on one stream
        # while we're blocked reading the other.
        _stderr_chunks: list[bytes] = []

        async def _drain_stderr() -> None:
            if proc.stderr:
                while True:
                    chunk = await proc.stderr.read(65536)
                    if not chunk:
                        break
                    _stderr_chunks.append(chunk)

        stderr_task = asyncio.create_task(_drain_stderr())

        try:
            # Stream stdout to log file
            async with aiofiles.open(log_file, mode="wb") as f:
                if proc.stdout:
                    while True:
                        chunk = await proc.stdout.read(65536)
                        if not chunk:
                            break
                        await f.write(chunk)

                        # Check if the watcher has flagged anomalies
                        if watcher.should_stop:
                            print(
                                f"[W{worker_id}] Batch {batch_index}: "
                                f"LogWatcher detected anomalies — killing process",
                                file=sys.stderr,
                            )
                            proc.kill()
                            watcher.stop()
                            await watcher_task
                            # Treat as a failure so circuit breaker can track it
                            return None

                # Wait for stderr drain to finish, then append to log so
                # startup errors (e.g. CLAUDECODE nested-session rejection)
                # are always visible in the captured log even when stdout is empty.
                await stderr_task
                stderr_bytes = b"".join(_stderr_chunks)
                if stderr_bytes:
                    stderr_line = json.dumps({
                        "type": "stderr",
                        "text": stderr_bytes.decode("utf-8", errors="replace"),
                    }) + "\n"
                    await f.write(stderr_line.encode())

            await asyncio.wait_for(proc.wait(), timeout=self.config.timeout_seconds)
        except asyncio.TimeoutError:
            proc.kill()
            print(f"[W{worker_id}] Batch {batch_index} timed out", file=sys.stderr)
            watcher.stop()
            await watcher_task
            return None
        finally:
            # Ensure watcher is stopped
            watcher.stop()
            if not watcher_task.done():
                try:
                    await asyncio.wait_for(watcher_task, timeout=2.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    watcher_task.cancel()
            # Ensure stderr drain task is cancelled if not yet done
            if not stderr_task.done():
                stderr_task.cancel()
                try:
                    await asyncio.wait_for(stderr_task, timeout=1.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass

        # --- Post-hoc log anomaly detection (kept for backward compat) ---
        anomalies = LogAnomalyDetector.scan_log(log_file)
        if anomalies:
            print(
                f"[W{worker_id}] Batch {batch_index}: {len(anomalies)} log anomaly(ies) detected:",
                file=sys.stderr,
            )
            for a in anomalies[:5]:  # cap output
                print(f"    \u26a0\ufe0f  {a}", file=sys.stderr)

            # Fatal anomalies (e.g. usage_limit) — immediately trip the
            # circuit breaker so ALL workers stop, not just this batch.
            if LogAnomalyDetector.has_fatal_anomaly(anomalies):
                raise CircuitBreakerTripped(
                    f"Fatal anomaly detected in batch {batch_index}: "
                    + "; ".join(a for a in anomalies if any(
                        a.startswith(f"{fn}:") for fn in LogAnomalyDetector._FATAL_PATTERNS
                    )),
                    self.circuit_breaker.get_stats(),
                )

        # --- Cost tracking: extract token usage from log ---
        usage = extract_token_usage_from_log(log_file)

        if (
            self.config.max_cache_read_tokens > 0
            and usage["cache_read_tokens"] > self.config.max_cache_read_tokens
        ):
            raise CircuitBreakerTripped(
                f"cache_read_tokens {usage['cache_read_tokens']:,} "
                f"exceeds limit {self.config.max_cache_read_tokens:,} "
                f"(batch {batch_index}, worker {worker_id})",
                self.circuit_breaker.get_stats(),
            )

        if self.cost_tracker:
            if (
                usage["input_tokens"] > 0
                or usage["output_tokens"] > 0
                or usage["cache_read_tokens"] > 0
                or usage["cache_creation_tokens"] > 0
            ):
                batch_cost = await self.cost_tracker.record_usage(
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    cache_read_tokens=usage["cache_read_tokens"],
                    cache_creation_tokens=usage["cache_creation_tokens"],
                    worker_id=worker_id,
                    batch_index=batch_index,
                )
                cost_stats = self.cost_tracker.get_stats()
                total_tokens = (
                    usage["input_tokens"]
                    + usage["output_tokens"]
                    + usage["cache_read_tokens"]
                    + usage["cache_creation_tokens"]
                )
                print(
                    f"[W{worker_id}] Batch {batch_index}: "
                    f"tokens={total_tokens:,} "
                    f"(in={usage['input_tokens']:,}, cache_read={usage['cache_read_tokens']:,}, "
                    f"cache_create={usage['cache_creation_tokens']:,}, out={usage['output_tokens']:,}); "
                    f"+${batch_cost:.4f}, total=${cost_stats['total_cost_usd']:.2f}/"
                    f"${cost_stats['max_budget_usd']:.2f}",
                )

        # Check result
        if proc.returncode != 0:
            # Before giving up, check if the log contains a partial result.
            # Claude CLI sometimes exits with returncode=1 when max_turns is
            # reached, but the log still contains ``{"type": "result",
            # "subtype": "success", "is_error": true, ...}`` with usable
            # output written to disk.
            partial_results = self._try_recover_partial(
                log_file, result_parse_path, directory_mode,
                worker_id, batch_index, timestamp,
            )
            if partial_results is not None:
                return partial_results

            # Genuine failure — save error log and return None
            # Use already-collected stderr bytes (proc.stderr pipe is already drained)
            stderr = b"".join(_stderr_chunks)
            self._save_error_log(worker_id, batch_index, timestamp, proc.returncode, stderr)
            print(
                f"[W{worker_id}] Claude failed for batch {batch_index} (exit {proc.returncode})",
                file=sys.stderr,
            )
            return None

        # Parse results from output file, fallback to log
        results = self._parse_results(result_parse_path)
        if not results:
            results = self._parse_results_from_log(log_file)
            if results:
                print(
                    f"[W{worker_id}] Batch {batch_index}: recovered {len(results)} result(s) from inline response",
                    file=sys.stderr,
                )

        # Clean up: delete intermediate file only in file mode
        if not directory_mode and result_parse_path.exists():
            result_parse_path.unlink()

        return results

    # ------------------------------------------------------------------
    # Partial result recovery
    # ------------------------------------------------------------------

    def _try_recover_partial(
        self,
        log_file: Path,
        result_parse_path: Path,
        directory_mode: bool,
        worker_id: int,
        batch_index: int,
        timestamp: int,
    ) -> list[dict[str, Any]] | None:
        """
        Attempt to recover partial results when Claude CLI exits with a
        non-zero return code.

        Claude CLI may exit with ``returncode=1`` even when it has
        produced usable output — for example when ``max_turns`` is
        reached.  In that case the stream-json log will contain a final
        ``{"type": "result", "subtype": "success", "is_error": true}``
        event, and the output file / directory may still hold valid data.

        Returns:
            A list of recovered result dicts, or ``None`` if recovery
            is not possible (i.e. the failure is genuine).
        """
        result_info = self._check_log_result_status(log_file)
        if result_info is None:
            # No result event in log at all — genuine crash / kill
            return None

        subtype = result_info.get("subtype", "")
        is_error = result_info.get("is_error", False)

        if subtype != "success":
            # e.g. subtype="error" — genuine failure
            return None

        # subtype=success, is_error=true — likely max_turns reached
        duration_s = result_info.get("duration_ms", 0) / 1000
        print(
            f"[W{worker_id}] Batch {batch_index}: Claude exited non-zero but "
            f"log shows subtype=success (is_error={is_error}, "
            f"duration={duration_s:.0f}s) — attempting partial recovery",
            file=sys.stderr,
        )

        # Try to parse whatever output was produced
        results = self._parse_results(result_parse_path)
        if not results:
            results = self._parse_results_from_log(log_file)

        if results:
            print(
                f"[W{worker_id}] Batch {batch_index}: "
                f"recovered {len(results)} partial result(s) from non-zero exit",
                file=sys.stderr,
            )
            # Clean up intermediate file
            if not directory_mode and result_parse_path.exists():
                result_parse_path.unlink()
            return results

        print(
            f"[W{worker_id}] Batch {batch_index}: "
            f"subtype=success but no parseable results found",
            file=sys.stderr,
        )
        return None

    @staticmethod
    def _check_log_result_status(log_file: Path) -> dict[str, Any] | None:
        """
        Scan a stream-json log for the final ``{"type": "result"}`` event
        and return its fields.

        Returns ``None`` if no result event is found (process was killed
        or crashed before producing one).
        """
        if not log_file.exists():
            return None

        last_result: dict[str, Any] | None = None
        try:
            with open(log_file, errors="replace") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict) and obj.get("type") == "result":
                            last_result = obj
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception:
            return None

        return last_result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_queue_payload(
        self,
        batch: list[dict[str, Any]],
        worker_id: int,
        context_file: str,
    ) -> dict[str, Any]:
        """Build the queue payload for Claude (ID-only)."""
        id_field = self.config.item_id_field
        item_ids = [str(item.get(id_field, f"item-{i}")) for i, item in enumerate(batch)]
        return {
            "worker_id": worker_id,
            "phase": self.config.phase_id,
            "item_ids": item_ids,
            "total_items": len(batch),
            "context_file": context_file,
        }

    def _build_context_payload(
        self,
        batch: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build the context payload (full item data keyed by ID, optionally filtered)."""
        id_field = self.config.item_id_field
        fields = self.config.context_fields
        result: dict[str, Any] = {}
        for i, item in enumerate(batch):
            key = str(item.get(id_field, f"item-{i}"))
            if fields:
                result[key] = {k: item[k] for k in fields if k in item}
            else:
                result[key] = item
        return result

    def _build_prompt(self, **kwargs) -> str:
        """Build the prompt content with arguments."""
        with open(self.config.prompt_path) as f:
            prompt_content = f.read()
        args = " ".join(f"{k.upper()}={v}" for k, v in kwargs.items())
        return f"{prompt_content}\n\n{args}"

    def _build_env(self, **kwargs) -> dict[str, str]:
        """Build environment variables for Claude execution."""
        env = os.environ.copy()

        # Remove Claude Code session variables that would trigger the nested-session
        # detection ("Claude Code cannot be launched inside another Claude Code
        # session").  The CLAUDECODE env var is set by Claude Code on startup and
        # inherited by every subprocess; child ``claude`` invocations see it and
        # immediately exit with code 1 (writing nothing to stdout).
        for var in ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID"):
            env.pop(var, None)

        env.update({
            "CLAUDE_CODE_PERMISSIONS": "bypassPermissions",
            "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "100000",
        })
        for key, value in kwargs.items():
            env[key.upper()] = str(value)
        return env

    def _get_phase_mcp_config(self) -> Path:
        """Generate a filtered MCP config containing only the servers this phase needs.

        Reads the project ``.mcp.json``, keeps only the servers listed in
        ``self.config.mcp_servers``, and writes the result to a deterministic
        path so it can be reused across workers of the same phase.
        """
        config_dir = Path("outputs/.mcp_configs")
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / f"mcp_{self.config.phase_id}.json"

        # Reuse if already generated (deterministic per phase)
        if config_path.exists():
            return config_path

        base_mcp = Path(".mcp.json")
        if base_mcp.exists():
            with open(base_mcp) as f:
                base_config = json.load(f)
        else:
            base_config = {"mcpServers": {}}

        needed = set(self.config.mcp_servers or [])
        filtered = {
            "mcpServers": {
                name: srv
                for name, srv in base_config.get("mcpServers", {}).items()
                if name in needed
            }
        }

        with open(config_path, "w") as f:
            json.dump(filtered, f, indent=2)

        return config_path

    def _build_cmd(self, prompt_content: str) -> list[str]:
        """Build the Claude CLI command."""
        cmd = [
            "claude",
            "--dangerously-skip-permissions",
            "--verbose",
            "--output-format", "stream-json",
            "-p", prompt_content,
        ]
        if self.config.model:
            cmd.extend(["--model", self.config.model])
        if self.config.max_turns_per_batch:
            cmd.extend(["--max-turns", str(self.config.max_turns_per_batch)])
        # Tool whitelist: restrict which tool definitions are sent to the API
        if self.config.tools_filter is not None:
            cmd.extend(["--tools", ",".join(self.config.tools_filter)])
        # MCP server filtering: only start the servers this phase needs
        if self.config.mcp_servers is not None:
            mcp_config_path = self._get_phase_mcp_config()
            cmd.extend(["--strict-mcp-config", "--mcp-config", str(mcp_config_path)])
        return cmd

    def _save_json(self, path: Path, data: Any) -> None:
        """Save JSON data to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _save_error_log(
        self,
        worker_id: int,
        batch_index: int,
        timestamp: int,
        exit_code: int,
        stderr: bytes,
    ) -> None:
        """Save error information for debugging."""
        error_log_file = self.log_dir / f"{self.config.phase_id}_w{worker_id}b{batch_index}_{timestamp}.error.log"
        stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

        debug_text = ""
        debug_latest = Path(".claude/debug/latest")
        try:
            if debug_latest.exists():
                debug_text = debug_latest.read_text(errors="replace")
        except Exception:
            pass

        with open(error_log_file, "w") as f:
            f.write(f"exit_code={exit_code}\n")
            if stderr_text:
                f.write("\n[stderr]\n")
                f.write(stderr_text)
            if debug_text:
                f.write("\n[claude_debug_latest]\n")
                f.write(debug_text)

    def _normalize_result_data(self, data: Any) -> list[dict[str, Any]]:
        """
        Normalize parsed JSON data into a flat list of result dicts.

        Handles both raw lists and wrapper dicts with a known result key
        (e.g. {"sub_graphs": [...]}).
        """
        if self.config.phase_id == "02":
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
            if isinstance(data, dict):
                if self.config.result_key in data and isinstance(data[self.config.result_key], list):
                    return [item for item in data[self.config.result_key] if isinstance(item, dict)]
                return []
            return []

        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

        if isinstance(data, dict):
            for key in [self.config.result_key, "items", "results", "audit_items", "graphs", "specs"]:
                if key in data and isinstance(data[key], list):
                    return [item for item in data[key] if isinstance(item, dict)]
            return [data]

        return []

    def _parse_results_from_log(self, log_file: Path) -> list[dict[str, Any]]:
        """
        Fallback: extract results from inline text in the Claude CLI log.
        """
        if not log_file.exists():
            return []

        result_text = ""
        try:
            with open(log_file) as f:
                for line in f:
                    try:
                        msg = json.loads(line)
                        if msg.get("type") == "result" and msg.get("result"):
                            result_text = msg["result"]
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception:
            return []

        if not result_text:
            return []

        json_blocks = re.findall(r"```json\s*(.*?)```", result_text, re.DOTALL)

        results: list[dict[str, Any]] = []
        for block in json_blocks:
            try:
                data = json.loads(block.strip())
            except json.JSONDecodeError:
                continue
            results.extend(self._normalize_result_data(data))

        return results

    def _parse_results(self, output_path: Path) -> list[dict[str, Any]]:
        """Parse results from output file."""
        if not output_path.exists():
            return []
        try:
            with open(output_path) as f:
                data = json.load(f)
        except Exception:
            return []
        return self._normalize_result_data(data)
