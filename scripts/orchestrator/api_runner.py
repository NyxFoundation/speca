"""
API Runner Module — OpenAI-compatible alternative to ClaudeRunner.

Drop-in replacement for ClaudeRunner that uses the OpenAI chat completions
API (compatible with DeepSeek, OpenAI, and other providers) instead of the
Claude CLI.  Implements the same tool execution loop with Read, Grep, Glob,
and Write tools, maintaining full compatibility with the existing orchestrator.

Environment variables:
  - API_RUNNER_BASE_URL:  API base URL (default: https://openrouter.ai/api/v1)
  - API_RUNNER_API_KEY:   API key for authentication
  - API_RUNNER_MODEL:     Model ID override (default: deepseek/deepseek-r1)
"""

from __future__ import annotations

import asyncio
import glob as glob_mod
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from .config import PhaseConfig
from .paths import get_output_root
from .runner import CircuitBreaker, CircuitBreakerTripped, MaxTurnsExhausted
from .watchdog import CostTracker, BudgetExceeded


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "Read",
            "description": (
                "Read a file from the local filesystem. "
                "Returns file contents with line numbers. "
                "Use offset and limit to read specific ranges."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file to read",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (0-based)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to read",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Grep",
            "description": (
                "Search file contents using regex patterns (ripgrep-compatible). "
                "Returns matching lines with file paths and line numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory to search in",
                    },
                    "glob": {
                        "type": "string",
                        "description": "Glob pattern to filter files (e.g. '*.go')",
                    },
                    "context": {
                        "type": "integer",
                        "description": "Lines of context around each match",
                    },
                    "head_limit": {
                        "type": "integer",
                        "description": "Limit output to first N lines",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Glob",
            "description": (
                "Find files matching a glob pattern. "
                "Returns matching file paths sorted by modification time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match (e.g. '**/*.go', 'src/**/*.ts')",
                    },
                    "path": {
                        "type": "string",
                        "description": "Base directory to search in",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Write",
            "description": (
                "Write content to a file. Creates parent directories if needed. "
                "Overwrites existing files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file",
                    },
                },
                "required": ["file_path", "content"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def _execute_read(params: dict[str, Any]) -> str:
    """Execute the Read tool."""
    file_path = params["file_path"]
    offset = params.get("offset", 0)
    limit = params.get("limit", 2000)

    try:
        with open(file_path, "r", errors="replace") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return f"Error: File not found: {file_path}"
    except IsADirectoryError:
        return f"Error: {file_path} is a directory, not a file"
    except PermissionError:
        return f"Error: Permission denied: {file_path}"

    # Apply offset and limit
    selected = lines[offset : offset + limit]
    numbered = []
    for i, line in enumerate(selected, start=offset + 1):
        numbered.append(f"{i}\t{line.rstrip()}")

    if not numbered:
        return f"(empty file or offset {offset} beyond end of file with {len(lines)} lines)"

    result = "\n".join(numbered)
    if len(result) > 100_000:
        result = result[:100_000] + "\n... (truncated)"
    return result


def _execute_grep(params: dict[str, Any]) -> str:
    """Execute the Grep tool using ripgrep."""
    pattern = params["pattern"]
    path = params.get("path", ".")
    glob_filter = params.get("glob")
    context = params.get("context", 0)
    head_limit = params.get("head_limit", 250)

    cmd = ["rg", "--no-heading", "-n"]
    if context:
        cmd.extend(["-C", str(context)])
    if glob_filter:
        cmd.extend(["--glob", glob_filter])
    cmd.extend([pattern, path])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        output = result.stdout
    except FileNotFoundError:
        # Fallback to grep if rg not available
        cmd_fallback = ["grep", "-rn"]
        if context:
            cmd_fallback.extend([f"-C{context}"])
        cmd_fallback.extend([pattern, path])
        try:
            result = subprocess.run(
                cmd_fallback, capture_output=True, text=True, timeout=30,
            )
            output = result.stdout
        except Exception as e:
            return f"Error: grep failed: {e}"
    except subprocess.TimeoutExpired:
        return "Error: Search timed out after 30 seconds"

    if not output.strip():
        return "No matches found"

    lines = output.split("\n")
    if head_limit and len(lines) > head_limit:
        lines = lines[:head_limit]
        lines.append(f"... (truncated to {head_limit} lines)")

    result_text = "\n".join(lines)
    if len(result_text) > 100_000:
        result_text = result_text[:100_000] + "\n... (truncated)"
    return result_text


def _execute_glob(params: dict[str, Any]) -> str:
    """Execute the Glob tool."""
    pattern = params["pattern"]
    base_path = params.get("path", ".")

    full_pattern = os.path.join(base_path, pattern)
    matches = sorted(glob_mod.glob(full_pattern, recursive=True))

    if not matches:
        return "No matching files found"

    # Limit output
    if len(matches) > 500:
        matches = matches[:500]
        matches.append(f"... ({len(matches)} total, truncated)")

    return "\n".join(matches)


def _execute_write(params: dict[str, Any]) -> str:
    """Execute the Write tool."""
    file_path = params["file_path"]
    content = params["content"]

    try:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} bytes to {file_path}"
    except Exception as e:
        return f"Error writing file: {e}"


TOOL_EXECUTORS: dict[str, Any] = {
    "Read": _execute_read,
    "Grep": _execute_grep,
    "Glob": _execute_glob,
    "Write": _execute_write,
}


# ---------------------------------------------------------------------------
# API Runner
# ---------------------------------------------------------------------------

class APIRunner:
    """
    Executes audit batches via OpenAI-compatible API with tool execution.

    Drop-in replacement for ClaudeRunner. Uses the same run_batch() interface,
    circuit breaker, and cost tracker integration.
    """

    # Subclasses override these so the parent constructor's env fallback
    # picks runtime-appropriate defaults (e.g. OpenAI / Gemini / Ollama).
    DEFAULT_BASE_URL: str = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL: str = "deepseek/deepseek-r1"
    BASE_URL_ENV: str = "API_RUNNER_BASE_URL"
    API_KEY_ENV: str = "API_RUNNER_API_KEY"
    MODEL_ENV: str = "API_RUNNER_MODEL"
    RUNTIME_LABEL: str = "api"

    def __init__(
        self,
        config: PhaseConfig,
        semaphore: asyncio.Semaphore,
        max_retries: int = 2,
        circuit_breaker: CircuitBreaker | None = None,
        cost_tracker: CostTracker | None = None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.config = config
        self.semaphore = semaphore
        self.max_retries = max_retries
        self.circuit_breaker = circuit_breaker or CircuitBreaker(config)
        self.cost_tracker = cost_tracker

        # Resolution order for each setting: explicit kwarg > env var >
        # class default. This lets subclasses bake in the right defaults
        # while still respecting an operator-set env override.
        self.base_url = (
            base_url
            if base_url is not None
            else os.environ.get(self.BASE_URL_ENV, self.DEFAULT_BASE_URL)
        )
        self.api_key = (
            api_key if api_key is not None else os.environ.get(self.API_KEY_ENV, "")
        )
        self.model = (
            model
            if model is not None
            else os.environ.get(self.MODEL_ENV, self.DEFAULT_MODEL)
        )

        # Directories
        self.output_dir = get_output_root()
        self.log_dir = self.output_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Max turns for tool loop
        self.max_turns = config.max_turns_per_batch or 50

    async def run_batch(
        self,
        batch: list[dict[str, Any]],
        worker_id: int,
        batch_index: int,
    ) -> list[dict[str, Any]] | None:
        """
        Execute an API-based audit for a batch of items.

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
        """Internal: execute a single batch via API with tool loop."""
        timestamp = int(time.time())
        phase_id = self.config.phase_id

        # Build queue and context files (same format as ClaudeRunner)
        queue_path = self.output_dir / f"{phase_id}_ASYNC_QUEUE_W{worker_id}B{batch_index}_{timestamp}.json"
        context_path = self.output_dir / f"{phase_id}_CONTEXT_W{worker_id}B{batch_index}_{timestamp}.json"
        result_path = self.output_dir / f"{phase_id}_PARTIAL_W{worker_id}B{batch_index}_{timestamp}.json"
        log_file = self.log_dir / f"{phase_id}_w{worker_id}b{batch_index}_{timestamp}.log.jsonl"

        # Build payloads
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

        # Build prompt from template
        prompt_content = self._build_prompt(
            worker_id=worker_id,
            queue_file=str(queue_path),
            context_file=str(context_path),
            batch_size=len(batch),
            iteration=batch_index,
            timestamp=timestamp,
            output_file=str(result_path),
        )

        # Run the conversation loop
        total_input_tokens = 0
        total_output_tokens = 0
        num_turns = 0
        log_entries: list[dict[str, Any]] = []

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompt_content},
        ]

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(300.0, connect=30.0),
        ) as client:
            for turn in range(self.max_turns):
                num_turns += 1

                request_body: dict[str, Any] = {
                    "model": self.model,
                    "messages": messages,
                    "tools": TOOL_DEFINITIONS,
                    "max_tokens": 16384,
                }

                log_entries.append({
                    "type": "api_request",
                    "turn": turn,
                    "timestamp": time.time(),
                    "model": self.model,
                    "message_count": len(messages),
                })

                try:
                    response = await client.post(
                        "/chat/completions",
                        json=request_body,
                    )
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    error_text = e.response.text[:500] if e.response else str(e)
                    log_entries.append({
                        "type": "api_error",
                        "turn": turn,
                        "status": e.response.status_code if e.response else 0,
                        "error": error_text,
                    })
                    # Check for rate limiting
                    if e.response and e.response.status_code == 429:
                        retry_after = int(e.response.headers.get("retry-after", "10"))
                        await asyncio.sleep(retry_after)
                        continue
                    raise
                except httpx.TimeoutException:
                    log_entries.append({
                        "type": "api_timeout",
                        "turn": turn,
                    })
                    raise

                data = response.json()
                usage = data.get("usage", {})
                total_input_tokens += usage.get("prompt_tokens", 0)
                total_output_tokens += usage.get("completion_tokens", 0)

                log_entries.append({
                    "type": "api_response",
                    "turn": turn,
                    "usage": usage,
                    "finish_reason": data.get("choices", [{}])[0].get("finish_reason"),
                })

                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                finish_reason = choice.get("finish_reason")

                # Append assistant message to conversation
                messages.append(message)

                # Check if model wants to call tools
                tool_calls = message.get("tool_calls")
                if tool_calls:
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        tool_name = func.get("name", "")
                        try:
                            tool_args = json.loads(func.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            tool_args = {}

                        log_entries.append({
                            "type": "tool_use",
                            "turn": turn,
                            "tool": tool_name,
                            "args_summary": {
                                k: (v[:100] if isinstance(v, str) and len(v) > 100 else v)
                                for k, v in tool_args.items()
                            },
                        })

                        # Execute tool
                        executor = TOOL_EXECUTORS.get(tool_name)
                        if executor:
                            try:
                                tool_result = executor(tool_args)
                            except Exception as e:
                                tool_result = f"Error executing {tool_name}: {e}"
                        else:
                            tool_result = f"Error: Unknown tool '{tool_name}'"

                        # Truncate very large tool results
                        if len(tool_result) > 80_000:
                            tool_result = tool_result[:80_000] + "\n... (truncated)"

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": tool_result,
                        })

                    # Continue loop — model will process tool results
                    continue

                # No tool calls — model has finished
                # Check if it wrote the result file
                if result_path.exists():
                    break

                # If finish_reason is "stop" and no tool calls, we're done
                if finish_reason == "stop":
                    break

            else:
                # Exhausted max_turns
                if result_path.exists():
                    # Got results despite hitting turn limit
                    pass
                else:
                    # Save log and raise
                    self._save_log(log_file, log_entries)
                    raise MaxTurnsExhausted(
                        f"Batch {batch_index} exhausted {self.max_turns} turns "
                        f"without producing output"
                    )

        # Save conversation log
        self._save_log(log_file, log_entries)

        # Cost tracking
        if self.cost_tracker and (total_input_tokens > 0 or total_output_tokens > 0):
            batch_cost = await self.cost_tracker.record_usage(
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                num_turns=num_turns,
                worker_id=worker_id,
                batch_index=batch_index,
            )
            cost_stats = self.cost_tracker.get_stats()
            print(
                f"[W{worker_id}] Batch {batch_index}: "
                f"tokens={total_input_tokens + total_output_tokens:,} "
                f"(in={total_input_tokens:,}, out={total_output_tokens:,}, "
                f"turns={num_turns}); "
                f"+${batch_cost:.4f}, total=${cost_stats['total_cost_usd']:.2f}/"
                f"${cost_stats['max_budget_usd']:.2f}",
            )

        # Parse results
        results = self._parse_results(result_path)
        if results is None:
            # Try to extract results from the last assistant message
            results = self._extract_results_from_response(messages)

        if results is None:
            print(
                f"[W{worker_id}] Batch {batch_index}: no results parsed",
                file=sys.stderr,
            )
            return None

        return results

    def _build_prompt(self, **kwargs: Any) -> str:
        """Build the prompt content with template substitution."""
        with open(self.config.prompt_path) as f:
            prompt_content = f.read()

        def _quote(v: Any) -> str:
            s = str(v)
            if " " in s or '"' in s:
                return f'"{s}"'
            return s

        args = " ".join(f"{k.upper()}={_quote(v)}" for k, v in kwargs.items())
        return f"{prompt_content}\n\n{args}"

    def _parse_results(self, result_path: Path) -> list[dict[str, Any]] | None:
        """Parse results from the output JSON file."""
        if not result_path.exists():
            return None

        try:
            with open(result_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        return self._normalize_result_data(data)

    def _normalize_result_data(self, data: Any) -> list[dict[str, Any]]:
        """Normalize result data to a flat list (same logic as ClaudeRunner)."""
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

        if isinstance(data, dict):
            result_key = self.config.result_key
            # Try result_key, then common alternatives
            for key in [result_key, "items", "results", "audit_items", "reviewed_items"]:
                if key in data and isinstance(data[key], list):
                    return [item for item in data[key] if isinstance(item, dict)]
            # If dict has no known list key, wrap it
            return [data]

        return []

    def _extract_results_from_response(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | None:
        """Try to extract JSON results from the last assistant message."""
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            if not content:
                continue

            # Try to find JSON in the response
            json_match = re.search(
                r'```json\s*\n(.*?)\n```',
                content,
                re.DOTALL,
            )
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                    return self._normalize_result_data(data)
                except json.JSONDecodeError:
                    pass

            # Try raw JSON parse
            for start_char in ["{", "["]:
                idx = content.find(start_char)
                if idx >= 0:
                    try:
                        data = json.loads(content[idx:])
                        return self._normalize_result_data(data)
                    except json.JSONDecodeError:
                        pass

        return None

    def _save_json(self, path: Path, data: Any) -> None:
        """Save JSON data to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _save_log(self, path: Path, entries: list[dict[str, Any]]) -> None:
        """Save log entries as JSONL."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Multi-runtime subclasses
#
# Each subclass exists *only* to bake in the right base_url / api_key env
# / model defaults for one provider. The whole tool-execution loop, cost
# tracker, circuit breaker, and result normaliser are inherited from
# :class:`APIRunner` because all three of these providers speak the OpenAI
# chat-completions function-calling wire format:
#
#   * OpenAI (codex CLI authenticates against this):
#       https://api.openai.com/v1/chat/completions
#   * Gemini's OpenAI compatibility layer (added late 2024):
#       https://generativelanguage.googleapis.com/v1beta/openai/chat/completions
#   * Ollama:
#       <host>/v1/chat/completions   (host: https://ollama.com OR a self-
#       hosted endpoint like http://localhost:11434)
#
# GitHub Copilot is intentionally NOT subclassed here: ``gh copilot
# suggest`` is a single-shot suggestion API with no tool-calling protocol,
# so it cannot drive the audit pipeline. The CLI keeps it registered for
# the chat side (see web/server/services/chat_runtime_copilot.py) and the
# orchestrator surface refuses to start an audit run against it.
# ---------------------------------------------------------------------------


class CodexAPIRunner(APIRunner):
    """OpenAI codex authenticates against the standard OpenAI Chat API.

    We accept ``OPENAI_API_KEY`` because it is the canonical name (and the
    one ``codex login --with-api-key`` writes into the env). Model defaults
    to ``gpt-4o``; set ``OPENAI_MODEL`` (or pass ``--model`` on the CLI) to
    pick a different model.
    """

    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MODEL = "gpt-4o"
    BASE_URL_ENV = "OPENAI_BASE_URL"
    API_KEY_ENV = "OPENAI_API_KEY"
    MODEL_ENV = "OPENAI_MODEL"
    RUNTIME_LABEL = "codex"


class GeminiAPIRunner(APIRunner):
    """Google Gemini's OpenAI compatibility endpoint.

    Requires ``GEMINI_API_KEY`` from Google AI Studio. The base URL is
    Google's compatibility shim that maps OpenAI chat/completions calls
    onto the Gemini API; tool-calling works identically.
    """

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
    DEFAULT_MODEL = "gemini-2.0-flash"
    BASE_URL_ENV = "GEMINI_BASE_URL"
    API_KEY_ENV = "GEMINI_API_KEY"
    MODEL_ENV = "GEMINI_MODEL"
    RUNTIME_LABEL = "gemini"


class OllamaAPIRunner(APIRunner):
    """Ollama via its OpenAI-compatible endpoint.

    Host comes from ``OLLAMA_HOST`` (cloud default: ``https://ollama.com``;
    self-hosted convention: ``http://localhost:11434``). Cloud calls
    require ``OLLAMA_API_KEY`` as a Bearer token; self-hosted does not.
    Model defaults to ``llama3.2``.
    """

    DEFAULT_BASE_URL = "https://ollama.com/v1"
    DEFAULT_MODEL = "llama3.2"
    BASE_URL_ENV = "OLLAMA_BASE_URL"  # explicit override
    API_KEY_ENV = "OLLAMA_API_KEY"
    MODEL_ENV = "OLLAMA_MODEL"
    RUNTIME_LABEL = "ollama"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # If the operator set OLLAMA_HOST but not OLLAMA_BASE_URL, derive
        # the chat-completions base URL from it. This matches the same
        # convention the Web chat runtime uses (web/server/services/
        # chat_runtime_ollama.py) so toggling between cloud / self-hosted
        # is a single env var.
        if (
            os.environ.get(self.BASE_URL_ENV) is None
            and (host := os.environ.get("OLLAMA_HOST"))
        ):
            host = host.rstrip("/")
            if "://" not in host:
                host = f"http://{host}"
            self.base_url = f"{host}/v1"
