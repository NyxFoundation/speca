"""Dispatch a chat-stream request to the appropriate runtime backend.

Three runtimes are wired today (see :mod:`runtime_preferences`):

* ``claude`` — Anthropic. Internally splits between the SDK path (for API
  keys) and the ``claude`` CLI subprocess (for claude.ai OAuth) by
  inspecting the credential prefix. This is the historical default.
* ``codex`` — OpenAI's ``codex`` CLI via ``codex exec --json``.
* ``ollama`` — Ollama's HTTP API (cloud or self-hosted).

The router (:mod:`web.server.routers.chat`) calls :func:`stream_response`
exactly once per turn. Each backend yields the same event shape
documented in ``docs/UI_DESIGN.md`` §7.2, so the SPA's ``useChatStream``
parser does not need to branch on runtime.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import AsyncIterator

from web.server.services import (
    chat_runtime,
    chat_runtime_cli,
    chat_runtime_codex,
    chat_runtime_copilot,
    chat_runtime_gemini,
    chat_runtime_ollama,
    runtime_preferences,
)
from web.server.services.chat_runtime import _OAUTH_TOKEN_PREFIX, get_api_key

logger = logging.getLogger(__name__)


async def stream_response(
    conversation_id: str,
    user_text: str,
    *,
    base: Path | None = None,
) -> AsyncIterator[dict]:
    """Dispatch to the runtime selected in :class:`RuntimePreferences`."""

    prefs = runtime_preferences.load()
    runtime = prefs.runtime

    if runtime == "codex":
        async for ev in chat_runtime_codex.stream_response(
            conversation_id=conversation_id,
            user_text=user_text,
            base=base,
            model=prefs.codex_model,
        ):
            yield ev
        return

    if runtime == "gemini":
        async for ev in chat_runtime_gemini.stream_response(
            conversation_id=conversation_id,
            user_text=user_text,
            base=base,
            model=prefs.gemini_model,
        ):
            yield ev
        return

    if runtime == "ollama":
        async for ev in chat_runtime_ollama.stream_response(
            conversation_id=conversation_id,
            user_text=user_text,
            base=base,
            prefs=prefs,
        ):
            yield ev
        return

    if runtime == "copilot":
        async for ev in chat_runtime_copilot.stream_response(
            conversation_id=conversation_id,
            user_text=user_text,
            base=base,
        ):
            yield ev
        return

    # Default: claude. Within this branch, route OAuth users through the
    # CLI subprocess (subscription routing) and API-key users through the
    # SDK (custom tools).
    credential = get_api_key()
    use_cli = isinstance(credential, str) and credential.startswith(_OAUTH_TOKEN_PREFIX)
    if use_cli:
        async for ev in chat_runtime_cli.stream_response(
            conversation_id=conversation_id,
            user_text=user_text,
            base=base,
        ):
            yield ev
        return

    async for ev in chat_runtime.stream_response(
        conversation_id=conversation_id,
        user_text=user_text,
    ):
        yield ev
