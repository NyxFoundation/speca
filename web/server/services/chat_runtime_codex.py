"""CLI-subprocess runtime for OpenAI's ``codex`` CLI.

Symmetric to :mod:`chat_runtime_cli` (the claude variant) — we spawn the
``codex exec`` command with ``--json`` so we can parse JSONL events and
map them onto the SPA's existing SSE wire (``content_block_delta`` /
``message_stop`` / ``error``). Multi-turn continuity is via
``codex exec resume <session_id>``; the session id is stashed under
``codex_session_id`` in the conversation file (extra="allow" makes the
schema round-trip transparent).

Auth model: the user runs ``codex login`` themselves (either ChatGPT plan
paste-code or ``codex login --with-api-key < OPENAI_API_KEY``); we do
not script that flow. The diagnostics page surfaces login status so the
SPA can prompt when needed.

Tool surface: codex's tool calls are internal and require user approval
in the regular CLI flow. Because the chat panel is a read-only Q&A
surface (no filesystem writes / shell), we pass ``--dangerously-bypass-
approvals-and-sandbox`` with a tight ``--sandbox read-only`` so codex
can browse the codebase but cannot mutate the workspace.
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


def _resolve_codex_bin() -> str | None:
    found = shutil.which("codex")
    if found is None and sys.platform == "win32":
        found = shutil.which("codex.cmd")
    return found


def _windows_creation_flags() -> int:
    return 0x08000000 if sys.platform == "win32" else 0


def _get_codex_session_id(conversation: Any) -> str | None:
    sid = getattr(conversation, "codex_session_id", None)
    if isinstance(sid, str) and sid:
        return sid
    extra = getattr(conversation, "model_extra", None)
    if isinstance(extra, dict):
        sid = extra.get("codex_session_id")
        if isinstance(sid, str) and sid:
            return sid
    return None


def _save_codex_session_id(
    conversation_id: str, session_id: str, base: Path | None
) -> None:
    conversation = chat_history.load_conversation(conversation_id, base=base)
    if conversation is None:
        return
    updated = conversation.model_copy(update={"codex_session_id": session_id})
    chat_history.save_conversation(updated, base=base)


def _build_cmd(
    prompt_text: str,
    resume_session_id: str | None,
    model: str | None,
) -> list[str]:
    codex_bin = _resolve_codex_bin()
    if codex_bin is None:
        raise RuntimeError("codex CLI not found on PATH")

    cmd: list[str] = [codex_bin, "exec"]
    # JSONL stream so we can parse events.
    cmd.append("--json")
    # Read-only sandbox + skip approvals so we can run non-interactively.
    # The CLI's surface for this is conservative; we keep the operator-
    # facing flags explicit instead of pulling them in via config.toml.
    cmd.extend(["--sandbox", "read-only"])
    cmd.append("--skip-git-repo-check")
    if model:
        cmd.extend(["--model", model])

    if resume_session_id:
        # ``exec resume <sid> <prompt>``
        cmd.extend(["resume", resume_session_id])
    cmd.append(prompt_text)
    return cmd


def _line_to_events(
    raw: str,
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    """Map one codex JSONL line onto SPA SSE events.

    codex exec --json emits events with a ``msg`` envelope:
        {"id": "...", "msg": {"type": "agent_message_delta", "delta": "..."}}
        {"id": "...", "msg": {"type": "agent_message", "message": "..."}}
        {"id": "...", "msg": {"type": "session_configured", "session_id": "..."}}
        {"id": "...", "msg": {"type": "task_complete", ...}}
        {"id": "...", "msg": {"type": "error", "message": "..."}}
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

    msg = payload.get("msg")
    if not isinstance(msg, dict):
        return []
    mtype = msg.get("type")

    if mtype == "session_configured":
        sid = msg.get("session_id") or payload.get("session_id")
        if isinstance(sid, str) and sid:
            state["codex_session_id"] = sid
        return []

    if mtype == "agent_message_delta":
        delta = msg.get("delta")
        if isinstance(delta, str) and delta:
            state["assistant_text"] = state.get("assistant_text", "") + delta
            return [{"type": "content_block_delta", "delta": {"text": delta}}]
        return []

    if mtype == "agent_message":
        # Fallback when partials aren't emitted — coalesced full message.
        if state.get("assistant_text"):
            return []
        text = msg.get("message")
        if isinstance(text, str) and text:
            state["assistant_text"] = text
            return [{"type": "content_block_delta", "delta": {"text": text}}]
        return []

    if mtype == "task_complete":
        # codex returns the final assistant message under ``last_agent_message``.
        last = msg.get("last_agent_message")
        out_events: list[dict[str, Any]] = []
        if (
            not state.get("assistant_text")
            and isinstance(last, str)
            and last
        ):
            state["assistant_text"] = last
            out_events.append(
                {"type": "content_block_delta", "delta": {"text": last}}
            )
        usage = msg.get("usage") or {}
        out_events.append({"type": "message_stop", "usage": usage})
        return out_events

    if mtype == "error":
        text = msg.get("message") or "codex reported error"
        return [
            {
                "type": "error",
                "reason": "runtime_error",
                "message": str(text),
            }
        ]

    return []


def _user_text_block(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": text}]


async def stream_response(
    conversation_id: str,
    user_text: str,
    *,
    base: Path | None = None,
    model: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream a response via ``codex exec --json`` (drop-in for claude variant)."""

    conversation = chat_history.ensure_conversation(conversation_id, base=base)
    chat_history.append_message(
        conversation, role="user", content=_user_text_block(user_text), base=base
    )

    resume = _get_codex_session_id(conversation)
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

    state: dict[str, Any] = {"assistant_text": "", "codex_session_id": None}

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
            "message": f"failed to spawn codex CLI: {exc}",
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
        logger.exception("chat_runtime_codex: read failed (%s)", exc)
        yield {
            "type": "error",
            "reason": "runtime_error",
            "message": f"codex read failed: {exc}",
        }
    finally:
        rc = await proc.wait()
        if rc != 0 and not state.get("assistant_text"):
            yield {
                "type": "error",
                "reason": "runtime_error",
                "message": f"codex CLI exited with code {rc}",
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
    sid = state.get("codex_session_id")
    if isinstance(sid, str) and sid:
        try:
            _save_codex_session_id(conversation_id, sid, base=base)
        except Exception as exc:  # pragma: no cover - non-fatal
            logger.warning("chat_runtime_codex: save session id failed (%s)", exc)
