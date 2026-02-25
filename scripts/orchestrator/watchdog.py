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

    # Maximum tool_call blocks before flagging as excessive.
    # Phase 03 processes up to 25 items per batch, each requiring multiple
    # tool calls (file reads, writes, etc.), so 50 is far too low.
    tool_call_threshold: int = 200

    # Maximum number of lines to scan (safety cap for huge logs)
    max_lines: int = 100_000


# Pre-compiled anomaly patterns applied ONLY to extracted error text,
# NOT to raw log lines (which contain embedded user content).
_ANOMALY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("rate_limit_error", re.compile(r"rate.?limit|429|too many requests", re.IGNORECASE)),
    ("context_overflow", re.compile(r"context.?length|token.?limit|maximum.?context", re.IGNORECASE)),
    ("api_error", re.compile(r"APIError|InternalServerError|ServiceUnavailable|overloaded", re.IGNORECASE)),
    ("timeout_error", re.compile(r"timed?\s*out|deadline exceeded|ETIMEDOUT", re.IGNORECASE)),
    ("usage_limit", re.compile(r"out of (?:extra )?usage|usage.?limit|resets? \w+ \d+", re.IGNORECASE)),
]

# Fatal patterns that should trigger IMMEDIATE stop (threshold=1).
# These indicate systemic issues that cannot be resolved by retrying.
_FATAL_PATTERNS: frozenset[str] = frozenset({"usage_limit"})

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

    # 5. Result events — scan the result text for usage limit messages.
    #    When Claude CLI hits a usage limit, it emits a result event with
    #    is_error=true and the result text contains the limit message.
    if msg_type == "result":
        result_text = obj.get("result", "")
        is_error = obj.get("is_error", False)
        subtype = obj.get("subtype", "")
        if is_error and isinstance(result_text, str) and result_text:
            # Only scan a short prefix to avoid false positives from
            # large result payloads that happen to contain trigger words
            return (result_text[:500], False)

    # For assistant/user/other messages, do NOT scan content for anomalies
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
        # Flag to ensure excessive_tool_calls is only counted once
        self._tool_call_flagged = False
        # Flag for fatal anomalies (e.g. usage_limit) — immediate stop
        self._fatal_detected = False

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
                    with open(self.log_path, "rb") as f:
                        f.seek(offset)
                        raw_data = f.read()
                        offset = f.tell()
                    new_data = raw_data.decode("utf-8", errors="replace")

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

        # Final read after stop to capture any remaining data
        try:
            size = self.log_path.stat().st_size
            if size > offset:
                with open(self.log_path, "rb") as f:
                    f.seek(offset)
                    raw_data = f.read()
                new_data = raw_data.decode("utf-8", errors="replace")
                for line in new_data.splitlines():
                    self._scan_line(line)
                    self.lines_scanned += 1
        except Exception:
            pass

    def _scan_line(self, line: str) -> None:
        """
        Scan a single log line for anomaly patterns.

        Uses ``_extract_scannable_text()`` to parse the JSON structure and
        only inspect error/system fields — NOT user content that may contain
        domain-specific terms like "429", "rate limit", "timeout" etc.

        Fatal patterns (e.g. usage_limit) are flagged for immediate stop
        regardless of the anomaly threshold.
        """
        text_to_scan, is_tool_use = _extract_scannable_text(line)

        if is_tool_use:
            self.tool_call_count += 1

        if text_to_scan:
            for name, pattern in _ANOMALY_PATTERNS:
                if pattern.search(text_to_scan):
                    desc = f"{name}: {text_to_scan.strip()[:200]}"
                    self.anomalies.append(desc)
                    # Mark fatal patterns for immediate stop
                    if name in _FATAL_PATTERNS:
                        self._fatal_detected = True

    def _check_threshold(self) -> bool:
        """Check if anomaly counts exceed thresholds.  Returns True to stop."""
        total_anomalies = len(self.anomalies)

        # FATAL patterns (e.g. usage_limit) trigger immediate stop
        # regardless of the anomaly threshold — these are systemic issues
        # that cannot be resolved by retrying.
        if self._fatal_detected:
            self._stop_event.set()
            print(
                f"\n🛑  LogWatcher: FATAL anomaly detected — immediate stop",
                file=sys.stderr,
            )
            for a in self.anomalies[-5:]:
                print(f"    🛑  {a}", file=sys.stderr)
            return True

        # Only flag excessive tool calls ONCE (not on every subsequent line)
        if (
            self.tool_call_count > self.cfg.tool_call_threshold
            and not self._tool_call_flagged
        ):
            self._tool_call_flagged = True
            self.anomalies.append(
                f"excessive_tool_calls: {self.tool_call_count} tool_call blocks "
                f"(threshold={self.cfg.tool_call_threshold})"
            )
            total_anomalies = len(self.anomalies)

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
            "fatal_detected": self._fatal_detected,
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
    "input_per_million": 3.00,    # $3.00 / 1M input tokens
    "output_per_million": 15.00,  # $15.00 / 1M output tokens
    "cache_read_multiplier": 0.10,     # billed at ~10% of input price
    "cache_creation_multiplier": 1.25, # billed at ~125% of input price (5m tier)
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
    cache_read_multiplier: float = _DEFAULT_PRICING["cache_read_multiplier"]
    cache_creation_multiplier: float = _DEFAULT_PRICING["cache_creation_multiplier"]

    # Accumulated counters
    total_input_tokens: int = field(default=0, init=False)
    total_output_tokens: int = field(default=0, init=False)
    total_cache_read_tokens: int = field(default=0, init=False)
    total_cache_creation_tokens: int = field(default=0, init=False)
    total_cost_usd: float = field(default=0.0, init=False)
    total_turns: int = field(default=0, init=False)
    batch_count: int = field(default=0, init=False)

    # Per-batch history for diagnostics
    _history: list[dict[str, Any]] = field(default_factory=list, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def record_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
        num_turns: int = 0,
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
        cache_read_cost = (
            (cache_read_tokens / 1_000_000)
            * self.input_price_per_million
            * self.cache_read_multiplier
        )
        cache_creation_cost = (
            (cache_creation_tokens / 1_000_000)
            * self.input_price_per_million
            * self.cache_creation_multiplier
        )
        output_cost = (output_tokens / 1_000_000) * self.output_price_per_million
        batch_cost = input_cost + cache_read_cost + cache_creation_cost + output_cost

        async with self._lock:
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_cache_read_tokens += cache_read_tokens
            self.total_cache_creation_tokens += cache_creation_tokens
            self.total_cost_usd += batch_cost
            self.total_turns += num_turns
            self.batch_count += 1

            self._history.append({
                "batch": self.batch_count,
                "worker_id": worker_id,
                "batch_index": batch_index,
                "input_tokens": input_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cache_creation_tokens": cache_creation_tokens,
                "output_tokens": output_tokens,
                "num_turns": num_turns,
                "batch_cost_usd": round(batch_cost, 4),
                "cumulative_cost_usd": round(self.total_cost_usd, 4),
            })

            if self.total_cost_usd > self.max_budget_usd:
                raise BudgetExceeded(
                    f"Budget exceeded: ${self.total_cost_usd:.2f} > "
                    f"${self.max_budget_usd:.2f} "
                    f"(after {self.batch_count} batches, "
                    f"{self.total_input_tokens + self.total_output_tokens + self.total_cache_read_tokens + self.total_cache_creation_tokens:,} total tokens)",
                    stats=self.get_stats(),
                )

        return batch_cost

    def get_stats(self) -> dict[str, Any]:
        """Return a snapshot of all cost counters."""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "total_cache_creation_tokens": self.total_cache_creation_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": (
                self.total_input_tokens
                + self.total_cache_read_tokens
                + self.total_cache_creation_tokens
                + self.total_output_tokens
            ),
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
            "total_turns": self.total_turns,
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

    The stream-json format emits one JSON object per line.  The ``result``
    event (emitted at the end of a successful run) carries authoritative
    cumulative totals and ``num_turns``.  When the process was killed before
    emitting a ``result`` event, we fall back to summing per-message usage
    (deduplicated by message ID to avoid double-counting duplicate events
    within the same API turn).

    Returns a dict with keys: ``input_tokens``, ``output_tokens``,
    ``cache_read_tokens``, ``cache_creation_tokens``, ``num_turns``.
    """
    if not isinstance(log_path, Path):
        log_path = Path(log_path)

    _ZERO: dict[str, int] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "num_turns": 0,
    }

    if not log_path.exists():
        return dict(_ZERO)

    result_usage: dict | None = None
    result_num_turns: int = 0
    # Per-message usage for fallback (message_id -> best usage snapshot)
    msg_usage: dict[str, dict[str, int]] = {}
    msg_order: list[str] = []

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

                if not isinstance(obj, dict):
                    continue

                # --- Prefer the result event (authoritative totals) ---
                if obj.get("type") == "result":
                    u = obj.get("usage")
                    if isinstance(u, dict):
                        result_usage = u
                        result_num_turns = obj.get("num_turns", 0) or 0
                    continue

                # --- Collect per-message usage for fallback ---
                msg_id: str | None = None
                usage: dict | None = None

                if "message" in obj and isinstance(obj["message"], dict):
                    msg = obj["message"]
                    msg_id = msg.get("id")
                    if "usage" in msg and isinstance(msg["usage"], dict):
                        usage = msg["usage"]
                elif "usage" in obj and isinstance(obj["usage"], dict):
                    usage = obj["usage"]

                if usage:
                    # Use message ID for dedup; fall back to sequential key
                    # for events that lack a message ID.
                    key = msg_id or f"__anon_{len(msg_order)}"
                    # Keep max of each field per message (events for the
                    # same message report identical or cumulative values).
                    prev = msg_usage.get(key)
                    if prev is None:
                        msg_order.append(key)
                        msg_usage[key] = {
                            "input_tokens": usage.get("input_tokens", 0),
                            "output_tokens": usage.get("output_tokens", 0),
                            "cache_read": usage.get("cache_read_input_tokens", 0),
                            "cache_creation": usage.get("cache_creation_input_tokens", 0),
                        }
                    else:
                        prev["input_tokens"] = max(prev["input_tokens"], usage.get("input_tokens", 0))
                        prev["output_tokens"] = max(prev["output_tokens"], usage.get("output_tokens", 0))
                        prev["cache_read"] = max(prev["cache_read"], usage.get("cache_read_input_tokens", 0))
                        prev["cache_creation"] = max(prev["cache_creation"], usage.get("cache_creation_input_tokens", 0))

    except Exception:
        pass

    # --- Build result ---
    if result_usage is not None:
        # Result event has authoritative totals
        return {
            "input_tokens": result_usage.get("input_tokens", 0),
            "output_tokens": result_usage.get("output_tokens", 0),
            "cache_read_tokens": result_usage.get("cache_read_input_tokens", 0),
            "cache_creation_tokens": result_usage.get("cache_creation_input_tokens", 0),
            "num_turns": result_num_turns,
        }

    # Fallback: sum per-message values
    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_creation_tokens = 0
    for mid in msg_order:
        u = msg_usage[mid]
        input_tokens += u["input_tokens"]
        output_tokens += u["output_tokens"]
        cache_read_tokens += u["cache_read"]
        cache_creation_tokens += u["cache_creation"]

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "num_turns": max(1, len(msg_order) // 2) if msg_order else 0,
    }
