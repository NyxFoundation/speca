"""GitHub Copilot orchestrator runner.

Wraps the agentic ``@github/copilot`` CLI as an audit-pipeline driver.

Unlike APIRunner subclasses (codex / gemini / ollama), Copilot is not
exposed via an OpenAI-compatible HTTP endpoint, so we cannot reuse the
chat-completions tool loop. Instead, we spawn the ``copilot`` CLI in
agentic mode and let it run its own tool loop (Read / Grep / Write /
shell are all enabled via ``--allow-all-tools``). The runner then:

1. Builds the audit prompt the same way ClaudeRunner / APIRunner do
   (template + queue file + context file).
2. Spawns ``copilot -p <prompt> --output-format json --allow-all-tools
   --no-banner`` and streams its JSONL events to a log file.
3. Watches for the ``session.*`` boot event (logged), ``error`` /
   ``policy.error`` events (raised as failures), and any usage payload
   on the terminal event (fed to CostTracker if non-zero).
4. After the subprocess exits, reads the result JSON file (if the
   agent used the Write tool to materialise it) or falls back to a
   ``​​​​json …`` block extracted from the accumulated assistant text.

Auth is owned by the CLI: the user runs ``copilot`` once interactively
to OAuth into GitHub; we never touch its credential cache.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import aiofiles

from .config import PhaseConfig
from .paths import get_output_root
from .runner import CircuitBreaker, CircuitBreakerTripped, MaxTurnsExhausted
from .watchdog import BudgetExceeded, CostTracker

logger = logging.getLogger(__name__)


def _resolve_copilot_bin() -> str | None:
    """Locate the agentic ``copilot`` CLI on PATH (resolved per-call so
    tests / probes can mock ``shutil.which`` without import-time binding)."""

    found = shutil.which("copilot")
    if found is None and sys.platform == "win32":
        found = shutil.which("copilot.cmd")
    return found


class CopilotRunner:
    """Drives the agentic copilot CLI as an audit batch worker.

    Constructor signature matches ClaudeRunner / APIRunner so base.py
    can swap it in based on the runtime registry decision.
    """

    RUNTIME_LABEL = "copilot"

    def __init__(
        self,
        config: PhaseConfig,
        semaphore: asyncio.Semaphore,
        max_retries: int = 2,
        circuit_breaker: CircuitBreaker | None = None,
        cost_tracker: CostTracker | None = None,
        *,
        model: str | None = None,
    ):
        self.config = config
        self.semaphore = semaphore
        self.max_retries = max_retries
        self.circuit_breaker = circuit_breaker or CircuitBreaker(config)
        self.cost_tracker = cost_tracker
        self.model = (
            model if model is not None else os.environ.get("COPILOT_MODEL")
        )

        self.output_dir = get_output_root()
        self.log_dir = self.output_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    async def run_batch(
        self,
        batch: list[dict[str, Any]],
        worker_id: int,
        batch_index: int,
    ) -> list[dict[str, Any]] | None:
        async with self.semaphore:
            for attempt in range(self.max_retries + 1):
                try:
                    result = await self._execute_batch(batch, worker_id, batch_index)
                    if result is not None:
                        if len(result) == 0:
                            await self.circuit_breaker.record_empty_result()
                            print(
                                f"[W{worker_id}] Batch {batch_index}: empty result set",
                                file=sys.stderr,
                            )
                        else:
                            await self.circuit_breaker.record_success()
                        return result
                except (CircuitBreakerTripped, BudgetExceeded):
                    raise
                except MaxTurnsExhausted as e:
                    print(f"[W{worker_id}] {e}", file=sys.stderr)
                    return []
                except Exception as e:
                    print(
                        f"[W{worker_id}] Batch {batch_index} attempt {attempt + 1} failed: {e}",
                        file=sys.stderr,
                    )

                if attempt < self.max_retries:
                    await self.circuit_breaker.record_retry()
                    await asyncio.sleep(2 ** attempt)

            await self.circuit_breaker.record_failure()
            return None

    async def _execute_batch(
        self,
        batch: list[dict[str, Any]],
        worker_id: int,
        batch_index: int,
    ) -> list[dict[str, Any]] | None:
        bin_ = _resolve_copilot_bin()
        if bin_ is None:
            raise RuntimeError(
                "copilot CLI not found on PATH. Install via "
                "`npm install -g @github/copilot`."
            )

        timestamp = int(time.time())
        phase_id = self.config.phase_id

        queue_path = self.output_dir / f"{phase_id}_ASYNC_QUEUE_W{worker_id}B{batch_index}_{timestamp}.json"
        context_path = self.output_dir / f"{phase_id}_CONTEXT_W{worker_id}B{batch_index}_{timestamp}.json"
        result_path = self.output_dir / f"{phase_id}_PARTIAL_W{worker_id}B{batch_index}_{timestamp}.json"
        log_file = self.log_dir / f"{phase_id}_w{worker_id}b{batch_index}_{timestamp}.log.jsonl"

        id_field = self.config.item_id_field
        item_ids = [str(item.get(id_field, f"item-{i}")) for i, item in enumerate(batch)]
        queue_payload = {
            "worker_id": worker_id,
            "phase": phase_id,
            "item_ids": item_ids,
            "total_items": len(batch),
            "context_file": str(context_path),
        }

        fields = self.config.context_fields
        context_payload: dict[str, Any] = {}
        for i, item in enumerate(batch):
            key = str(item.get(id_field, f"item-{i}"))
            if fields:
                context_payload[key] = {k: item[k] for k in fields if k in item}
            else:
                context_payload[key] = item

        self._save_json(queue_path, queue_payload)
        self._save_json(context_path, context_payload)

        prompt_content = self._build_prompt(
            worker_id=worker_id,
            queue_file=str(queue_path),
            context_file=str(context_path),
            batch_size=len(batch),
            iteration=batch_index,
            timestamp=timestamp,
            output_file=str(result_path),
        )

        cmd = self._build_cmd(bin_, prompt_content)
        creation_flags = 0x08000000 if sys.platform == "win32" else 0

        state: dict[str, Any] = {
            "assistant_text": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "error_message": None,
            "session_id": None,
            "tool_count": 0,
            "saw_complete": False,
        }

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.config.workdir or str(Path.cwd()),
            creationflags=creation_flags,
        )

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
            async with aiofiles.open(log_file, mode="wb") as f:
                if proc.stdout:
                    while True:
                        raw = await proc.stdout.readline()
                        if not raw:
                            break
                        await f.write(raw)
                        line = raw.decode("utf-8", errors="replace")
                        self._consume_event(line, state)

            await asyncio.wait_for(proc.wait(), timeout=self.config.timeout_seconds)
            await stderr_task
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            stderr_task.cancel()
            print(
                f"[W{worker_id}] Batch {batch_index} timed out",
                file=sys.stderr,
            )
            return None
        finally:
            if proc.returncode is None:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
            if not stderr_task.done():
                stderr_task.cancel()
                try:
                    await asyncio.wait_for(stderr_task, timeout=1.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass

        stderr_bytes = b"".join(_stderr_chunks)
        if stderr_bytes:
            try:
                with open(log_file, "ab") as f:
                    line = (
                        json.dumps(
                            {
                                "type": "stderr",
                                "text": stderr_bytes.decode("utf-8", errors="replace"),
                            }
                        )
                        + "\n"
                    )
                    f.write(line.encode())
            except OSError:
                pass

        if self.cost_tracker:
            input_tokens = state["input_tokens"]
            output_tokens = state["output_tokens"]
            if input_tokens > 0 or output_tokens > 0:
                batch_cost = await self.cost_tracker.record_usage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    num_turns=state["tool_count"],
                    worker_id=worker_id,
                    batch_index=batch_index,
                )
                cost_stats = self.cost_tracker.get_stats()
                print(
                    f"[W{worker_id}] Batch {batch_index}: "
                    f"tokens={input_tokens + output_tokens:,} "
                    f"(in={input_tokens:,}, out={output_tokens:,}, "
                    f"tools={state['tool_count']}); "
                    f"+${batch_cost:.4f}, total=${cost_stats['total_cost_usd']:.2f}/"
                    f"${cost_stats['max_budget_usd']:.2f}",
                )

        if state["error_message"]:
            print(
                f"[W{worker_id}] Batch {batch_index}: copilot reported error: "
                f"{state['error_message'][:200]}",
                file=sys.stderr,
            )
            return None

        if proc.returncode != 0:
            print(
                f"[W{worker_id}] Batch {batch_index}: copilot exited code {proc.returncode}",
                file=sys.stderr,
            )
            recovered = self._parse_results(result_path)
            if recovered:
                return recovered
            return None

        results = self._parse_results(result_path)
        if results is None:
            results = self._extract_results_from_text(state["assistant_text"])

        if results is None:
            print(
                f"[W{worker_id}] Batch {batch_index}: no results parsed",
                file=sys.stderr,
            )
            return None

        return results

    # ------------------------------------------------------------------
    # Event consumption
    # ------------------------------------------------------------------

    def _consume_event(self, raw: str, state: dict[str, Any]) -> None:
        """Update accumulator state from one Copilot JSONL line.

        Mirrors the event taxonomy parsed by
        ``web/server/services/chat_runtime_copilot.py::_line_to_events``
        but tailored for orchestrator needs (track tokens / tool count /
        terminal errors instead of emitting SSE frames).
        """

        line = raw.strip()
        if not line:
            return
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return

        event_type = payload.get("type") or ""
        raw_data = payload.get("data")
        data = raw_data if isinstance(raw_data, dict) else {}

        if event_type.startswith("session.") and event_type != "session.end":
            sid = (
                data.get("sessionId")
                or data.get("session_id")
                or payload.get("sessionId")
                or payload.get("session_id")
            )
            if isinstance(sid, str) and sid:
                state["session_id"] = sid
            return

        if event_type in ("assistant.delta", "message.delta", "text.delta"):
            text = data.get("text") or data.get("delta")
            if isinstance(text, dict):
                text = text.get("text")
            if isinstance(text, str) and text:
                state["assistant_text"] += text
            return

        if event_type in ("assistant.message", "message", "completion"):
            if state["assistant_text"]:
                return
            message = data.get("message") or data.get("content") or data
            text = ""
            if isinstance(message, dict):
                text = message.get("text") or message.get("content") or ""
            elif isinstance(message, str):
                text = message
            if text:
                state["assistant_text"] = text
            return

        if event_type.startswith("tool."):
            if event_type in ("tool.start", "tool.call"):
                state["tool_count"] += 1
            return

        if event_type in ("error", "policy.error"):
            msg = (
                data.get("message")
                or payload.get("message")
                or "copilot reported error"
            )
            state["error_message"] = str(msg)
            return

        if event_type in ("session.end", "complete", "done", "finish"):
            usage = data.get("usage") or payload.get("usage") or {}
            if isinstance(usage, dict):
                state["input_tokens"] = int(
                    usage.get("input_tokens")
                    or usage.get("prompt_tokens")
                    or state["input_tokens"]
                )
                state["output_tokens"] = int(
                    usage.get("output_tokens")
                    or usage.get("completion_tokens")
                    or state["output_tokens"]
                )
            state["saw_complete"] = True
            return

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_cmd(self, bin_: str, prompt_content: str) -> list[str]:
        cmd: list[str] = [
            bin_,
            "-p",
            prompt_content,
            "--output-format",
            "json",
            "--allow-all-tools",
            "--no-banner",
        ]
        if self.model:
            cmd.extend(["--model", self.model])
        return cmd

    def _build_prompt(self, **kwargs: Any) -> str:
        with open(self.config.prompt_path, encoding="utf-8") as f:
            prompt_content = f.read()

        def _quote(v: Any) -> str:
            s = str(v)
            if " " in s or '"' in s:
                return f'"{s}"'
            return s

        args = " ".join(f"{k.upper()}={_quote(v)}" for k, v in kwargs.items())
        return f"{prompt_content}\n\n{args}"

    def _save_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _parse_results(self, result_path: Path) -> list[dict[str, Any]] | None:
        if not result_path.exists():
            return None
        try:
            with open(result_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
        return self._normalize_result_data(data)

    def _normalize_result_data(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            result_key = self.config.result_key
            for key in [
                result_key,
                "items",
                "results",
                "audit_items",
                "reviewed_items",
            ]:
                if key in data and isinstance(data[key], list):
                    return [item for item in data[key] if isinstance(item, dict)]
            return [data]
        return []

    def _extract_results_from_text(self, text: str) -> list[dict[str, Any]] | None:
        if not text:
            return None
        json_match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return self._normalize_result_data(data)
            except json.JSONDecodeError:
                pass
        for start_char in ["{", "["]:
            idx = text.find(start_char)
            if idx >= 0:
                try:
                    data = json.loads(text[idx:])
                    return self._normalize_result_data(data)
                except json.JSONDecodeError:
                    pass
        return None
