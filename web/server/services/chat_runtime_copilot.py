"""GitHub Copilot CLI runtime.

Wraps ``gh copilot`` (the official GitHub Copilot CLI shim, downloaded
on demand by ``gh``) so the SPA chat panel can drive it. Copilot's
non-interactive surface is intentionally narrow:

* ``gh copilot suggest -t <type> "<prompt>"`` — single-shot completion.
* ``gh copilot explain "<command>"`` — explain a shell command.

It does NOT expose a streaming JSONL chat API like claude / codex /
gemini. We therefore run ``gh copilot suggest`` non-interactively,
capture stdout in full, and emit the result as a single
``content_block_delta`` followed by ``message_stop``. This is functional
for short turns ("how do I X") but obviously less rich than the streaming
runtimes — the right v1 surface here is via Copilot's hypothetical
``/chat`` API once it exists.

Auth model: the user must run ``gh auth login`` and have Copilot enabled
on their account. We do not script that. The diagnostics page reports
``gh auth status`` so the SPA can prompt when needed.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
from pathlib import Path
from typing import Any, AsyncIterator

from web.server.services import chat_history

logger = logging.getLogger(__name__)


def _resolve_gh_bin() -> str | None:
    found = shutil.which("gh")
    if found is None and sys.platform == "win32":
        found = shutil.which("gh.exe")
    return found


def _windows_creation_flags() -> int:
    return 0x08000000 if sys.platform == "win32" else 0


def _user_text_block(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": text}]


async def stream_response(
    conversation_id: str,
    user_text: str,
    *,
    base: Path | None = None,
    model: str | None = None,  # accepted for symmetry; ignored
) -> AsyncIterator[dict[str, Any]]:
    """Issue one ``gh copilot suggest`` and emit the response as one delta."""

    conversation = chat_history.ensure_conversation(conversation_id, base=base)
    chat_history.append_message(
        conversation, role="user", content=_user_text_block(user_text), base=base
    )

    gh = _resolve_gh_bin()
    if gh is None:
        yield {
            "type": "error",
            "reason": "runtime_error",
            "message": (
                "gh CLI not found on PATH. Install GitHub CLI from "
                "https://cli.github.com/ and run `gh auth login`."
            ),
        }
        yield {"type": "message_stop", "usage": {}}
        return

    # gh copilot's prompt argument is positional; we keep ``-t shell`` as
    # the default suggestion type because most chat traffic on a SPECA
    # audit dashboard is shell- / git- / GitHub-related. The user can
    # prefix their question with "explain:" / "git:" / "gh:" and we'll
    # honour that hint.
    suggest_type = "shell"
    prompt_for_copilot = user_text
    lower = user_text.lstrip().lower()
    if lower.startswith("git:"):
        suggest_type = "git"
        prompt_for_copilot = user_text.split(":", 1)[1].strip()
    elif lower.startswith("gh:"):
        suggest_type = "gh"
        prompt_for_copilot = user_text.split(":", 1)[1].strip()
    elif lower.startswith("explain:"):
        suggest_type = "shell"
        prompt_for_copilot = user_text.split(":", 1)[1].strip()

    cmd = [
        gh,
        "copilot",
        "suggest",
        "-t",
        suggest_type,
        prompt_for_copilot,
    ]

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
            "message": f"failed to spawn gh copilot: {exc}",
        }
        yield {"type": "message_stop", "usage": {}}
        return

    assert proc.stdout is not None
    chunks: list[str] = []
    try:
        # gh copilot is interactive by default — if it asks us to confirm
        # or for an "execute / revise / explain" choice, just close
        # stdin via wait. Read until EOF.
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            chunks.append(raw.decode("utf-8", errors="replace"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("chat_runtime_copilot: read failed (%s)", exc)
        yield {
            "type": "error",
            "reason": "runtime_error",
            "message": f"gh copilot read failed: {exc}",
        }

    rc = await proc.wait()
    full = "".join(chunks).strip()

    if rc != 0 and not full:
        yield {
            "type": "error",
            "reason": "runtime_error",
            "message": f"gh copilot exited with code {rc}",
        }
        yield {"type": "message_stop", "usage": {}}
        return

    if full:
        yield {"type": "content_block_delta", "delta": {"text": full}}
        fresh = chat_history.load_conversation(conversation_id, base=base)
        if fresh is not None:
            chat_history.append_message(
                fresh,
                role="assistant",
                content=[{"type": "text", "text": full}],
                base=base,
            )

    yield {"type": "message_stop", "usage": {}}
