"""GitHub Copilot CLI runtime (agentic).

Wraps the official ``@github/copilot`` agentic CLI (``copilot``) — NOT
the older ``gh copilot suggest`` shim. The new CLI is a peer of
claude / codex / gemini:

* ``copilot -p <prompt> --output-format json`` emits JSONL events
* ``--allow-all-tools`` lets the agent use Read / Grep / shell tools
  non-interactively (required for chat-bot drive)
* ``--no-banner`` keeps stdout free of decorative output
* Sessions can be resumed via ``--resume <id>``

Event taxonomy (observed; tolerant parser keeps unknown types out of
the SSE stream):

* ``session.*`` — boot / mcp / warnings — surfaced via logger only
* ``message`` / ``assistant.message`` — final assistant text
* ``message.delta`` / ``assistant.delta`` — streaming text deltas
* ``tool.start`` / ``tool.result`` — informational; we do not surface
  them to the SPA because the chat panel does not own copilot's tool
  approval UX (the CLI already prompts when allow-all is off)
* ``error`` / ``policy.error`` — surfaced as ``runtime_error`` SSE

Auth: the user runs ``copilot`` once interactively to OAuth into GitHub
(the CLI handles the device flow). We do not script that. The
diagnostics + Settings pages report binary presence.
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


def _resolve_copilot_bin() -> str | None:
    """Locate the agentic ``copilot`` CLI on PATH (npm-installed)."""

    found = shutil.which("copilot")
    if found is None and sys.platform == "win32":
        found = shutil.which("copilot.cmd")
    return found


def _windows_creation_flags() -> int:
    return 0x08000000 if sys.platform == "win32" else 0


def _get_copilot_session_id(conversation: Any) -> str | None:
    sid = getattr(conversation, "copilot_session_id", None)
    if isinstance(sid, str) and sid:
        return sid
    extra = getattr(conversation, "model_extra", None)
    if isinstance(extra, dict):
        sid = extra.get("copilot_session_id")
        if isinstance(sid, str) and sid:
            return sid
    return None


def _save_copilot_session_id(
    conversation_id: str, session_id: str, base: Path | None
) -> None:
    conversation = chat_history.load_conversation(conversation_id, base=base)
    if conversation is None:
        return
    updated = conversation.model_copy(update={"copilot_session_id": session_id})
    chat_history.save_conversation(updated, base=base)


def _build_cmd(
    prompt_text: str, resume_session_id: str | None, model: str | None
) -> list[str]:
    bin_ = _resolve_copilot_bin()
    if bin_ is None:
        raise RuntimeError("copilot CLI not found on PATH")

    cmd: list[str] = [
        bin_,
        "-p",
        prompt_text,
        "--output-format",
        "json",
        # `--allow-all-tools` is what makes non-interactive mode work —
        # without it the CLI blocks waiting for tool-approval confirmations
        # on stdin (which we close).
        "--allow-all-tools",
        "--no-banner",
    ]
    if resume_session_id:
        cmd.extend(["--resume", resume_session_id])
    if model:
        cmd.extend(["--model", model])
    return cmd


def _user_text_block(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": text}]


def _line_to_events(
    raw: str,
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    """Map one Copilot JSONL event to zero-or-more SPA SSE events.

    Copilot's JSONL is hierarchical (every event has an ``id`` /
    ``parentId`` / ``timestamp`` envelope plus an event-specific
    ``data``). We sniff a small set of types that carry text or signal
    completion; everything else is logged at debug level.
    """

    line = raw.strip()
    if not line:
        return []
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []

    event_type = payload.get("type") or ""
    raw_data = payload.get("data")
    data = raw_data if isinstance(raw_data, dict) else {}

    # Session bootstrap — pick up the session id for `--resume` next turn.
    if event_type.startswith("session."):
        sid = (
            data.get("sessionId")
            or data.get("session_id")
            or payload.get("sessionId")
            or payload.get("session_id")
        )
        if isinstance(sid, str) and sid:
            state["copilot_session_id"] = sid
        return []

    # Streaming deltas. The event shape evolved over CLI versions, so we
    # check a few field names.
    if event_type in ("assistant.delta", "message.delta", "text.delta"):
        text = data.get("text") or data.get("delta")
        if isinstance(text, dict):
            text = text.get("text")
        if isinstance(text, str) and text:
            state["assistant_text"] = state.get("assistant_text", "") + text
            return [{"type": "content_block_delta", "delta": {"text": text}}]
        return []

    # Coalesced full message — used when partials aren't emitted.
    if event_type in ("assistant.message", "message", "completion"):
        if state.get("assistant_text"):
            return []
        message = data.get("message") or data.get("content") or data
        text = ""
        if isinstance(message, dict):
            text = message.get("text") or message.get("content") or ""
        elif isinstance(message, str):
            text = message
        if text:
            state["assistant_text"] = text
            return [{"type": "content_block_delta", "delta": {"text": text}}]
        return []

    # Tool calls are NOT surfaced to the SPA — the CLI already runs them
    # under our --allow-all-tools, and the SPA's approval UI is wired to
    # claude/codex's tool_use events, not copilot's. We log for debug.
    if event_type.startswith("tool."):
        logger.debug("copilot %s: %s", event_type, data)
        return []

    # Errors. Copilot emits both `error` (operator) and `policy.error`
    # (subscription / org policy refused the request).
    if event_type in ("error", "policy.error"):
        msg = data.get("message") or "copilot reported error"
        return [
            {
                "type": "error",
                "reason": "runtime_error",
                "message": str(msg),
            }
        ]

    if event_type in ("session.end", "complete", "done", "finish"):
        return [{"type": "message_stop", "usage": data.get("usage", {})}]

    return []


async def stream_response(
    conversation_id: str,
    user_text: str,
    *,
    base: Path | None = None,
    model: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream a response via the agentic ``copilot`` CLI."""

    conversation = chat_history.ensure_conversation(conversation_id, base=base)
    chat_history.append_message(
        conversation, role="user", content=_user_text_block(user_text), base=base
    )

    resume = _get_copilot_session_id(conversation)
    try:
        cmd = _build_cmd(user_text, resume, model)
    except RuntimeError as exc:
        yield {
            "type": "error",
            "reason": "runtime_error",
            "message": str(exc),
        }
        yield {"type": "message_stop", "usage": {}}
        return

    state: dict[str, Any] = {"assistant_text": "", "copilot_session_id": None}

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
            "message": f"failed to spawn copilot CLI: {exc}",
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
            line = raw.decode("utf-8", errors="replace")
            for event in _line_to_events(line, state):
                if event.get("type") == "message_stop":
                    saw_message_stop = True
                yield event
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("chat_runtime_copilot: read failed (%s)", exc)
        yield {
            "type": "error",
            "reason": "runtime_error",
            "message": f"copilot read failed: {exc}",
        }
    finally:
        rc = await proc.wait()
        if rc != 0 and not state.get("assistant_text"):
            yield {
                "type": "error",
                "reason": "runtime_error",
                "message": f"copilot CLI exited with code {rc}",
            }
        if not saw_message_stop:
            yield {"type": "message_stop", "usage": {}}

    text = state.get("assistant_text") or ""
    fresh = chat_history.load_conversation(conversation_id, base=base)
    if fresh is not None and text:
        chat_history.append_message(
            fresh,
            role="assistant",
            content=[{"type": "text", "text": text}],
            base=base,
        )
    sid = state.get("copilot_session_id")
    if isinstance(sid, str) and sid:
        try:
            _save_copilot_session_id(conversation_id, sid, base=base)
        except Exception as exc:  # pragma: no cover - non-fatal
            logger.warning("chat_runtime_copilot: save session id failed (%s)", exc)
