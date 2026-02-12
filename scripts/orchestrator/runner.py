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

    Note: For real-time monitoring during execution, use ``LogWatcher``
    from the ``watchdog`` module instead.
    """

    # Patterns that suggest the worker is stuck
    _ANOMALY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
        ("excessive_tool_calls", re.compile(r'"tool_calls":\s*\[', re.IGNORECASE)),
        ("rate_limit_error", re.compile(r"rate.?limit|429|too many requests", re.IGNORECASE)),
        ("context_overflow", re.compile(r"context.?length|token.?limit|maximum.?context", re.IGNORECASE)),
        ("repeated_error", re.compile(r"error.*error.*error", re.IGNORECASE)),
    ]

    # If the log contains more than this many tool_call blocks it's likely looping
    TOOL_CALL_THRESHOLD = 50

    @classmethod
    def scan_log(cls, log_path: Path | str) -> list[str]:
        """
        Scan a log file and return a list of anomaly descriptions.

        Returns an empty list if no anomalies are found.
        """
        if not isinstance(log_path, Path):
            log_path = Path(log_path)
        if not log_path.exists():
            return []

        anomalies: list[str] = []
        tool_call_count = 0

        try:
            with open(log_path, errors="replace") as f:
                for line in f:
                    for name, pattern in cls._ANOMALY_PATTERNS:
                        if pattern.search(line):
                            if name == "excessive_tool_calls":
                                tool_call_count += 1
                            else:
                                anomalies.append(f"{name}: {line.strip()[:200]}")
        except Exception:
            pass

        if tool_call_count > cls.TOOL_CALL_THRESHOLD:
            anomalies.append(
                f"excessive_tool_calls: {tool_call_count} tool_call blocks "
                f"(threshold={cls.TOOL_CALL_THRESHOLD})"
            )

        return anomalies


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
        prefix = self.config.output_prefix
        if prefix:
            partial_base = f"{phase_id}_{prefix}_PARTIAL"
        else:
            partial_base = f"{phase_id}_PARTIAL"
        queue_path = self.output_dir / f"{phase_id}_ASYNC_QUEUE_W{worker_id}B{batch_index}_{timestamp}.json"
        log_file = self.log_dir / f"{phase_id}_w{worker_id}b{batch_index}_{timestamp}.log.jsonl"

        # Determine output paths based on output_mode
        if directory_mode:
            batch_output_dir = self.output_dir / "graphs" / f"batch_w{worker_id}b{batch_index}_{timestamp}"
            batch_output_dir.mkdir(parents=True, exist_ok=True)
            result_parse_path = batch_output_dir / "index.json"
            output_kwargs: dict[str, str] = {"output_dir": str(batch_output_dir)}
        else:
            result_parse_path = self.output_dir / f"{partial_base}_W{worker_id}B{batch_index}_{timestamp}.json"
            output_kwargs = {"output_file": str(result_parse_path)}

        # Save queue
        queue_payload = self._build_queue_payload(batch, worker_id)
        self._save_json(queue_path, queue_payload)

        # Build prompt
        prompt_content = self._build_prompt(
            worker_id=worker_id,
            queue_file=str(queue_path),
            batch_size=len(batch),
            iteration=batch_index,
            timestamp=timestamp,
            **output_kwargs,
        )

        # Build command
        cmd = [
            "claude",
            "--dangerously-skip-permissions",
            "--verbose",
            "--output-format", "stream-json",
            "-p", prompt_content,
        ]

        # Build environment
        env = self._build_env(
            worker_id=worker_id,
            queue_file=str(queue_path),
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

        # --- Post-hoc log anomaly detection (kept for backward compat) ---
        anomalies = LogAnomalyDetector.scan_log(log_file)
        if anomalies:
            print(
                f"[W{worker_id}] Batch {batch_index}: {len(anomalies)} log anomaly(ies) detected:",
                file=sys.stderr,
            )
            for a in anomalies[:5]:  # cap output
                print(f"    ⚠️  {a}", file=sys.stderr)

        # --- Cost tracking: extract token usage from log ---
        if self.cost_tracker:
            usage = extract_token_usage_from_log(log_file)
            if usage["input_tokens"] > 0 or usage["output_tokens"] > 0:
                batch_cost = await self.cost_tracker.record_usage(
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    worker_id=worker_id,
                    batch_index=batch_index,
                )
                cost_stats = self.cost_tracker.get_stats()
                print(
                    f"[W{worker_id}] Batch {batch_index}: "
                    f"tokens={usage['input_tokens']+usage['output_tokens']:,} "
                    f"(+${batch_cost:.4f}, "
                    f"total=${cost_stats['total_cost_usd']:.2f}/"
                    f"${cost_stats['max_budget_usd']:.2f})",
                )

        # Check result
        if proc.returncode != 0:
            stderr = await proc.stderr.read() if proc.stderr else b""
            self._save_error_log(worker_id, batch_index, timestamp, proc.returncode, stderr)
            print(
                f"[W{worker_id}] Claude failed for batch {batch_index} (exit {proc.returncode})",
                file=sys.stderr,
            )
            return None

        # Parse results from output file / index.json, fallback to log
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
    # Helpers (unchanged from original)
    # ------------------------------------------------------------------

    def _build_queue_payload(
        self,
        batch: list[dict[str, Any]],
        worker_id: int,
    ) -> dict[str, Any]:
        """Build the queue payload for Claude."""
        return {
            "worker_id": worker_id,
            "phase": self.config.phase_id,
            "items": batch,
            "total_items": len(batch),
        }

    def _build_prompt(self, **kwargs) -> str:
        """Build the prompt content with arguments."""
        with open(self.config.prompt_path) as f:
            prompt_content = f.read()
        args = " ".join(f"{k.upper()}={v}" for k, v in kwargs.items())
        return f"{prompt_content}\n\n{args}"

    def _build_env(self, **kwargs) -> dict[str, str]:
        """Build environment variables for Claude execution."""
        env = os.environ.copy()
        env.update({
            "CLAUDE_CODE_PERMISSIONS": "bypassPermissions",
            "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "100000",
        })
        for key, value in kwargs.items():
            env[key.upper()] = str(value)
        return env

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
