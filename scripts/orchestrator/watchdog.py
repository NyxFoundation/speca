"""
Watchdog Module — Real-time Log Monitoring & Cost Tracking

Provides two complementary safety mechanisms that run alongside batch
execution to detect anomalies early and prevent runaway costs:

  - **LogWatcher**: Async task that tails a log file in real time,
    scanning each new line for anomaly patterns (rate limits, context
    overflow, repeated errors, excessive tool calls).  When anomalies
    exceed a configurable threshold the watcher sets an asyncio Event
    that the caller can check.

    **Important**: The watcher parses each line as JSON (Claude CLI
    stream-json format) and only inspects *structural* fields — top-level
    ``type``, ``error``, and ``subtype`` — to avoid false positives from
    user content embedded in ``tool_result`` or ``text`` blocks.

  - **CostTracker**: Accumulates per-batch token usage (input + output)
    and estimated dollar cost.  Raises ``BudgetExceeded`` when the
    cumulative cost crosses the configured ceiling.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Log Watcher — real-time async log tail with anomaly detection
# ---------------------------------------------------------------------------

@dataclass
class LogWatcherConfig:
    """Tunables for the real-time log watcher."""

    # How often (seconds) to poll the log file for new content
    poll_interval: float = 1.0

    # Number of anomaly hits before the watcher fires the stop event
    anomaly_threshold: int = 3

    # Maximum tool_call blocks before flagging as excessive
    tool_call_threshold: int = 50

    # Maximum number of lines to scan (safety cap for huge logs)
    max_lines: int = 100_000


# Pre-compiled anomaly patterns applied ONLY to extracted error text,
# NOT to raw log lines (which contain embedded user content).
_ANOMALY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("rate_limit_error", re.compile(r"rate.?limit|429|too many requests", re.IGNORECASE)),
    ("context_overflow", re.compile(r"context.?length|token.?limit|maximum.?context", re.IGNORECASE)),
    ("api_error", re.compile(r"APIError|InternalServerError|ServiceUnavailable|overloaded", re.IGNORECASE)),
    ("timeout_error", re.compile(r"timed?\s*out|deadline exceeded|ETIMEDOUT", re.IGNORECASE)),
]

_TOOL_CALL_PATTERN = re.compile(r'"type"\s*:\s*"tool_use"')


def _extract_scannable_text(line: str) -> tuple[str | None, bool]:
    """
    Parse a stream-json log line and extract ONLY structural/error text
    that should be scanned for anomalies.

    Returns:
        (text_to_scan, is_tool_use)
        - text_to_scan: a short string to match against anomaly patterns,
          or None if this line should be skipped entirely.
        - is_tool_use: True if this line represents a tool_use event.

    The key insight is that Claude CLI stream-json logs embed the full
    conversation — including user-provided content like security checklists
    — inside ``message.content[].text`` and ``tool_result.content`` fields.
    These fields naturally contain words like "429", "rate limit", "timeout",
    "error" etc. as part of the audit domain language, causing false positives
    when scanning raw lines.

    We therefore restrict scanning to:
      1. Lines with ``"type": "error"`` — actual API/system errors
      2. The ``subtype`` field of ``"type": "system"`` messages
      3. Top-level ``error`` objects (API error responses)
    """
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        # Not valid JSON — scan the raw line as a fallback
        # (e.g. stderr output mixed into the log)
        return (line.strip()[:500], False)

    if not isinstance(obj, dict):
        return (None, False)

    msg_type = obj.get("type", "")

    # 1. Actual error events from Claude CLI
    if msg_type == "error":
        error_obj = obj.get("error", {})
        if isinstance(error_obj, dict):
            # e.g. {"type": "error", "error": {"type": "rate_limit_error", "message": "..."}}
            error_text = f"{error_obj.get('type', '')} {error_obj.get('message', '')}"
            return (error_text, False)
        return (str(error_obj)[:500], False)

    # 2. System messages — check subtype for rate limit / overloaded signals
    if msg_type == "system":
        msg = obj.get("message", {})
        if isinstance(msg, dict):
            subtype = msg.get("subtype", "")
            content = msg.get("content", "")
            # Only scan the subtype and a short prefix of content
            if isinstance(content, str):
                return (f"{subtype} {content[:300]}", False)
            return (subtype, False)

    # 3. Top-level error field (some API responses)
    if "error" in obj and msg_type not in ("assistant", "user"):
        error_val = obj["error"]
        if isinstance(error_val, dict):
            return (f"{error_val.get('type', '')} {error_val.get('message', '')}", False)
        if isinstance(error_val, str):
            return (error_val[:500], False)

    # 4. Check for tool_use (for excessive tool call counting)
    is_tool_use = False
    if msg_type == "assistant":
        msg = obj.get("message", {})
        if isinstance(msg, dict):
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        is_tool_use = True
                        break

    # For assistant/user/result messages, do NOT scan content for anomalies
    return (None, is_tool_use)


class LogWatcher:
    """
    Asynchronously tails a log file and scans for anomaly patterns.

    Usage::

        watcher = LogWatcher(log_path)
        task = asyncio.create_task(watcher.watch())
        # ... run batch ...
        if watcher.should_stop:
            # anomaly threshold exceeded
        watcher.stop()
        await task
    """

    def __init__(
        self,
        log_path: Path | str,
        config: LogWatcherConfig | None = None,
    ):
        if not isinstance(log_path, Path):
            log_path = Path(log_path)
        self.log_path = log_path
        self.cfg = config or LogWatcherConfig()

        # Public state
        self.anomalies: list[str] = []
        self.tool_call_count: int = 0
        self.lines_scanned: int = 0

        # Stop event — set when anomaly threshold is exceeded
        self._stop_event = asyncio.Event()
        # Cancellation flag
        self._cancelled = False

    @property
    def should_stop(self) -> bool:
        """True when the watcher has detected enough anomalies to recommend stopping."""
        return self._stop_event.is_set()

    def stop(self) -> None:
        """Signal the watcher to stop tailing."""
        self._cancelled = True

    async def watch(self) -> None:
        """
        Main watch loop.  Tails the log file, scanning each new line.

        Exits when:
          - ``stop()`` is called
          - anomaly threshold is exceeded (sets ``_stop_event``)
          - max_lines is reached
        """
        # Wait for the file to appear (it may not exist yet when the
        # watcher starts before the subprocess writes its first line)
        for _ in range(30):
            if self.log_path.exists():
                break
            if self._cancelled:
                return
            await asyncio.sleep(self.cfg.poll_interval)
        else:
            return  # file never appeared

        offset = 0
        while not self._cancelled:
            try:
                size = self.log_path.stat().st_size
                if size > offset:
                    with open(self.log_path, "r", errors="replace") as f:
                        f.seek(offset)
                        new_data = f.read()
                        offset = f.tell()

                    for line in new_data.splitlines():
                        self._scan_line(line)
                        self.lines_scanned += 1

                        if self.lines_scanned >= self.cfg.max_lines:
                            self._cancelled = True
                            break

                        if self._check_threshold():
                            return
            except FileNotFoundError:
                pass  # file may be rotated / deleted
            except Exception:
                pass  # don't crash the watcher on unexpected errors

            await asyncio.sleep(self.cfg.poll_interval)

    def _scan_line(self, line: str) -> None:
        """
        Scan a single log line for anomaly patterns.

        Uses ``_extract_scannable_text()`` to parse the JSON structure and
        only inspect error/system fields — NOT user content that may contain
        domain-specific terms like "429", "rate limit", "timeout" etc.
        """
        text_to_scan, is_tool_use = _extract_scannable_text(line)

        if is_tool_use:
            self.tool_call_count += 1

        if text_to_scan:
            for name, pattern in _ANOMALY_PATTERNS:
                if pattern.search(text_to_scan):
                    desc = f"{name}: {text_to_scan.strip()[:200]}"
                    self.anomalies.append(desc)

    def _check_threshold(self) -> bool:
        """Check if anomaly counts exceed thresholds.  Returns True to stop."""
        total_anomalies = len(self.anomalies)
        if self.tool_call_count > self.cfg.tool_call_threshold:
            self.anomalies.append(
                f"excessive_tool_calls: {self.tool_call_count} tool_call blocks "
                f"(threshold={self.cfg.tool_call_threshold})"
            )
            total_anomalies += 1

        if total_anomalies >= self.cfg.anomaly_threshold:
            self._stop_event.set()
            print(
                f"\n⚠️  LogWatcher: anomaly threshold reached "
                f"({total_anomalies} anomalies, threshold={self.cfg.anomaly_threshold})",
                file=sys.stderr,
            )
            for a in self.anomalies[-5:]:
                print(f"    ⚠️  {a}", file=sys.stderr)
            return True
        return False

    def get_summary(self) -> dict[str, Any]:
        """Return a summary dict suitable for structured logging."""
        return {
            "log_path": str(self.log_path),
            "lines_scanned": self.lines_scanned,
            "anomaly_count": len(self.anomalies),
            "tool_call_count": self.tool_call_count,
            "should_stop": self.should_stop,
            "anomalies": self.anomalies[-10:],  # cap for readability
        }


# ---------------------------------------------------------------------------
# Cost Tracker — per-phase token & dollar budget enforcement
# ---------------------------------------------------------------------------

class BudgetExceeded(Exception):
    """Raised when the cumulative cost exceeds the configured budget."""

    def __init__(self, message: str, stats: dict[str, Any]):
        self.stats = stats
        super().__init__(message)


# Anthropic Claude pricing (per 1M tokens) — conservative estimates
# These can be overridden via CostTracker constructor.
_DEFAULT_PRICING = {
    "input_per_million": 3.00,   # $3.00 / 1M input tokens
    "output_per_million": 15.00,  # $15.00 / 1M output tokens
}


@dataclass
class CostTracker:
    """
    Tracks cumulative token usage and estimated dollar cost across batches.

    Thread-safe for use with asyncio (uses an asyncio Lock for updates).

    Usage::

        tracker = CostTracker(max_budget_usd=50.0)
        # after each batch:
        await tracker.record_usage(input_tokens=12000, output_tokens=3000)
        # raises BudgetExceeded if cumulative cost > max_budget_usd
    """

    max_budget_usd: float = 50.0
    input_price_per_million: float = _DEFAULT_PRICING["input_per_million"]
    output_price_per_million: float = _DEFAULT_PRICING["output_per_million"]

    # Accumulated counters
    total_input_tokens: int = field(default=0, init=False)
    total_output_tokens: int = field(default=0, init=False)
    total_cost_usd: float = field(default=0.0, init=False)
    batch_count: int = field(default=0, init=False)

    # Per-batch history for diagnostics
    _history: list[dict[str, Any]] = field(default_factory=list, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def record_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        *,
        worker_id: int = 0,
        batch_index: int = 0,
    ) -> float:
        """
        Record token usage for a single batch and return the incremental cost.

        Raises:
            BudgetExceeded: when cumulative cost exceeds ``max_budget_usd``.
        """
        input_cost = (input_tokens / 1_000_000) * self.input_price_per_million
        output_cost = (output_tokens / 1_000_000) * self.output_price_per_million
        batch_cost = input_cost + output_cost

        async with self._lock:
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_cost_usd += batch_cost
            self.batch_count += 1

            self._history.append({
                "batch": self.batch_count,
                "worker_id": worker_id,
                "batch_index": batch_index,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "batch_cost_usd": round(batch_cost, 4),
                "cumulative_cost_usd": round(self.total_cost_usd, 4),
            })

            if self.total_cost_usd > self.max_budget_usd:
                raise BudgetExceeded(
                    f"Budget exceeded: ${self.total_cost_usd:.2f} > "
                    f"${self.max_budget_usd:.2f} "
                    f"(after {self.batch_count} batches, "
                    f"{self.total_input_tokens + self.total_output_tokens:,} total tokens)",
                    stats=self.get_stats(),
                )

        return batch_cost

    def get_stats(self) -> dict[str, Any]:
        """Return a snapshot of all cost counters."""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "max_budget_usd": self.max_budget_usd,
            "budget_remaining_usd": round(
                max(0, self.max_budget_usd - self.total_cost_usd), 4
            ),
            "budget_utilization_pct": round(
                (self.total_cost_usd / self.max_budget_usd * 100)
                if self.max_budget_usd > 0
                else 0,
                1,
            ),
            "batch_count": self.batch_count,
        }

    def get_history(self) -> list[dict[str, Any]]:
        """Return the full per-batch cost history."""
        return list(self._history)


# ---------------------------------------------------------------------------
# Utility: extract token usage from Claude CLI stream-json log
# ---------------------------------------------------------------------------

def extract_token_usage_from_log(log_path: Path | str) -> dict[str, int]:
    """
    Parse a Claude CLI stream-json log and extract total token usage.

    The stream-json format emits one JSON object per line.  We look for
    ``usage`` objects that contain ``input_tokens`` and ``output_tokens``.

    Returns:
        {"input_tokens": N, "output_tokens": M}
    """
    if not isinstance(log_path, Path):
        log_path = Path(log_path)

    input_tokens = 0
    output_tokens = 0

    if not log_path.exists():
        return {"input_tokens": 0, "output_tokens": 0}

    try:
        with open(log_path, errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Claude CLI stream-json emits usage in various message types
                usage = None
                if isinstance(obj, dict):
                    # Direct usage field
                    if "usage" in obj and isinstance(obj["usage"], dict):
                        usage = obj["usage"]
                    # Nested in message
                    elif "message" in obj and isinstance(obj["message"], dict):
                        msg = obj["message"]
                        if "usage" in msg and isinstance(msg["usage"], dict):
                            usage = msg["usage"]

                if usage:
                    input_tokens = max(
                        input_tokens,
                        usage.get("input_tokens", 0),
                    )
                    output_tokens += usage.get("output_tokens", 0)

    except Exception:
        pass

    return {"input_tokens": input_tokens, "output_tokens": output_tokens}
