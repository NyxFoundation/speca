"""CLI-subprocess runtime for Google's ``gemini`` CLI.

Same shape as :mod:`chat_runtime_cli` and :mod:`chat_runtime_codex` — we
spawn ``gemini -p <prompt> --output-format stream-json`` and translate
its JSONL output into the SPA's SSE wire (``content_block_delta`` /
``message_stop`` / ``error``).

Auth model: the user provides ``GEMINI_API_KEY`` in their environment or
writes auth into ``~/.gemini/settings.json``. We shell out; we do not
manage tokens. Diagnostics surfaces login status.

Tool surface: gemini's tool calls are internal and gated by an approval
mode. We pass ``--approval-mode plan`` (read-only) so the chat panel is
safe to expose without consent prompts.

Stream-json parsing is tolerant: gemini's exact event shape has
evolved across versions, so we look for any ``text`` / ``content`` /
``delta`` field that carries a partial assistant message and emit it
verbatim. Unknown event types are dropped.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any, AsyncIterator

from web.server.services import chat_history

logger = logging.getLogger(__name__)


def _resolve_gemini_bin() -> str | None:
    found = shutil.which("gemini")
    if found is None and sys.platform == "win32":
        found = shutil.which("gemini.cmd")
    return found


def _windows_creation_flags() -> int:
    return 0x08000000 if sys.platform == "win32" else 0


def _build_cmd(prompt_text: str, model: str | None) -> list[str]:
    gem = _resolve_gemini_bin()
    if gem is None:
        raise RuntimeError("gemini CLI not found on PATH")

    cmd: list[str] = [
        gem,
        "-p",
        prompt_text,
        "--output-format",
        "stream-json",
        # Read-only mode; gemini will not edit files / run shell.
        "--approval-mode",
        "plan",
        # Trust the current workspace — required for non-interactive use,
        # safe because the SPA chat surface is sandboxed-by-design.
        "--skip-trust",
    ]
    if model:
        cmd.extend(["--model", model])
    return cmd


def _extract_text_delta(payload: Any) -> str | None:
    """Pull a text delta out of one gemini stream-json line.

    We tolerate a few common shapes:
      * ``{"type":"content","text":"..."}``
      * ``{"type":"text_delta","delta":"..."}``
      * ``{"event":"chunk","text":"..."}``
      * Google GenerateContentResponse: ``{"candidates":[{"content":{"parts":[{"text":"..."}]}}]}``
    """

    if not isinstance(payload, dict):
        return None
    for key in ("text", "delta", "content"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val
        if isinstance(val, dict):
            t = val.get("text") or val.get("delta")
            if isinstance(t, str) and t:
                return t

    candidates = payload.get("candidates")
    if isinstance(candidates, list):
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            content = cand.get("content")
            if isinstance(content, dict):
                parts = content.get("parts")
                if isinstance(parts, list):
                    chunks: list[str] = []
                    for p in parts:
                        if isinstance(p, dict):
                            t = p.get("text")
                            if isinstance(t, str) and t:
                                chunks.append(t)
                    if chunks:
                        return "".join(chunks)
    return None


def _is_final(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("done") is True:
        return True
    t = payload.get("type")
    if t in ("end", "complete", "finish", "message_stop"):
        return True
    if payload.get("finishReason") or payload.get("finish_reason"):
        return True
    return False


def _user_text_block(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": text}]


def _build_replay_prompt(conversation: Any, new_user_text: str) -> str:
    """Compose a single prompt string from history + new user text.

    gemini -p takes a single prompt argument, so multi-turn context is
    replayed in-band. We cap to the last 20 turns to keep argv short and
    the model focused.
    """

    lines: list[str] = []
    tail = list(conversation.messages)[-20:]
    for m in tail:
        role = m.role
        if role not in ("user", "assistant"):
            continue
        content = m.content
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    t = block.get("text")
                    if isinstance(t, str):
                        parts.append(t)
            text = "\n".join(parts)
        else:
            text = ""
        if text:
            label = "User" if role == "user" else "Assistant"
            lines.append(f"{label}: {text}")
    lines.append(f"User: {new_user_text}")
    lines.append("Assistant:")
    return "\n\n".join(lines)


async def stream_response(
    conversation_id: str,
    user_text: str,
    *,
    base: Path | None = None,
    model: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream a response via gemini CLI."""

    conversation = chat_history.ensure_conversation(conversation_id, base=base)
    chat_history.append_message(
        conversation, role="user", content=_user_text_block(user_text), base=base
    )
    conversation = chat_history.load_conversation(conversation_id, base=base)
    if conversation is None:  # pragma: no cover
        yield {
            "type": "error",
            "reason": "runtime_error",
            "message": "conversation disappeared after append",
        }
        yield {"type": "message_stop", "usage": {}}
        return

    prompt = _build_replay_prompt(conversation, user_text)
    try:
        cmd = _build_cmd(prompt, model)
    except RuntimeError as exc:
        yield {
            "type": "error",
            "reason": "runtime_error",
            "message": str(exc),
        }
        yield {"type": "message_stop", "usage": {}}
        return

    assistant_text = ""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            creationflags=_windows_creation_flags(),
        )
    except (OSError, FileNotFoundError) as exc:
        yield {
            "type": "error",
            "reason": "runtime_error",
            "message": f"failed to spawn gemini CLI: {exc}",
        }
        yield {"type": "message_stop", "usage": {}}
        return

    assert proc.stdout is not None
    saw_message_stop = False
    try:
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            delta = _extract_text_delta(payload)
            if delta:
                assistant_text += delta
                yield {"type": "content_block_delta", "delta": {"text": delta}}
            if _is_final(payload):
                yield {"type": "message_stop", "usage": {}}
                saw_message_stop = True
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("chat_runtime_gemini: read failed (%s)", exc)
        yield {
            "type": "error",
            "reason": "runtime_error",
            "message": f"gemini read failed: {exc}",
        }
    finally:
        rc = await proc.wait()
        if rc != 0 and not assistant_text:
            yield {
                "type": "error",
                "reason": "runtime_error",
                "message": f"gemini CLI exited with code {rc}",
            }
        if not saw_message_stop:
            yield {"type": "message_stop", "usage": {}}

    if assistant_text:
        fresh = chat_history.load_conversation(conversation_id, base=base)
        if fresh is not None:
            chat_history.append_message(
                fresh,
                role="assistant",
                content=[{"type": "text", "text": assistant_text}],
                base=base,
            )
