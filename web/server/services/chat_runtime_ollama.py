"""HTTP runtime for Ollama (cloud + self-hosted).

Ollama exposes two compatible streaming endpoints:

* ``POST /api/chat`` — Ollama's native shape. JSONL stream where each
  line is ``{"message": {"role": "assistant", "content": "..."}, "done": false}``
  (and the final line has ``done: true`` plus usage stats).
* ``POST /v1/chat/completions`` — OpenAI-compatible. We prefer ``/api/chat``
  because it works against the bare ``ollama serve`` running locally
  without an API key and against ``https://ollama.com`` with one.

Host resolution comes from :class:`RuntimePreferences.ollama_host` (the
SPA writes this from the Settings page). API key comes from the
``OLLAMA_API_KEY`` env var so it never gets persisted to disk by the SPA
— Settings just tells the user to export it, which mirrors the Ollama
CLI's own convention.

Multi-turn: Ollama is stateless on the wire so we replay the conversation
history (up to the last ~20 turns to keep the request tiny). Tools are
intentionally NOT enabled — the chat panel is read-only Q&A.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

from web.server.services import chat_history
from web.server.services.runtime_preferences import RuntimePreferences

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "llama3.2"
DEFAULT_HOST = "https://ollama.com"
MAX_TURNS_IN_CONTEXT = 20


def _user_text_block(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": text}]


def _ollama_messages_from_history(
    conversation: Any, new_user_text: str
) -> list[dict[str, str]]:
    """Reduce the on-disk history to the flat ``role/content`` shape Ollama wants."""

    out: list[dict[str, str]] = []
    tail = list(conversation.messages)[-MAX_TURNS_IN_CONTEXT:]
    for m in tail:
        role = m.role
        if role not in ("user", "assistant"):
            continue  # drop "system"-role meta rows (approvals etc.)
        content = m.content
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    t = block.get("text")
                    if isinstance(t, str):
                        parts.append(t)
            text = "\n".join(parts)
        else:
            text = ""
        if text:
            out.append({"role": role, "content": text})
    out.append({"role": "user", "content": new_user_text})
    return out


def _resolve_host(prefs: RuntimePreferences) -> str:
    host = (prefs.ollama_host or DEFAULT_HOST).rstrip("/")
    # Allow bare hostnames (``localhost:11434``) for the self-hosted path.
    if "://" not in host:
        host = f"http://{host}"
    return host


def _build_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/x-ndjson"}
    key = os.environ.get("OLLAMA_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


async def stream_response(
    conversation_id: str,
    user_text: str,
    *,
    base: Path | None = None,
    prefs: RuntimePreferences | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream a response via Ollama (cloud or self-hosted)."""

    # Lazy import to avoid a circular dep with the registry.
    if prefs is None:
        from web.server.services import runtime_preferences

        prefs = runtime_preferences.load()

    conversation = chat_history.ensure_conversation(conversation_id, base=base)
    chat_history.append_message(
        conversation, role="user", content=_user_text_block(user_text), base=base
    )
    # Reload so the new user message is in the prompt history.
    conversation = chat_history.load_conversation(conversation_id, base=base)
    if conversation is None:  # pragma: no cover - we just wrote it
        yield {
            "type": "error",
            "reason": "runtime_error",
            "message": "conversation disappeared after append",
        }
        yield {"type": "message_stop", "usage": {}}
        return

    host = _resolve_host(prefs)
    model = prefs.ollama_model or DEFAULT_MODEL
    body = {
        "model": model,
        "messages": _ollama_messages_from_history(conversation, user_text)[:-1]
        + [{"role": "user", "content": user_text}],
        "stream": True,
    }

    assistant_text = ""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0)) as client:
            async with client.stream(
                "POST",
                f"{host}/api/chat",
                json=body,
                headers=_build_headers(),
            ) as resp:
                if resp.status_code >= 400:
                    # Drain the body so the connection can be reused / closed
                    # cleanly. The response is short for errors.
                    err = await resp.aread()
                    yield {
                        "type": "error",
                        "reason": "runtime_error",
                        "message": (
                            f"Ollama HTTP {resp.status_code}: "
                            f"{err.decode('utf-8', errors='replace')[:400]}"
                        ),
                    }
                    yield {"type": "message_stop", "usage": {}}
                    return

                async for raw in resp.aiter_lines():
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue

                    msg = payload.get("message")
                    if isinstance(msg, dict):
                        chunk = msg.get("content")
                        if isinstance(chunk, str) and chunk:
                            assistant_text += chunk
                            yield {
                                "type": "content_block_delta",
                                "delta": {"text": chunk},
                            }

                    if payload.get("done"):
                        usage = {
                            k: payload.get(k)
                            for k in (
                                "prompt_eval_count",
                                "eval_count",
                                "total_duration",
                            )
                            if k in payload
                        }
                        yield {"type": "message_stop", "usage": usage}
                        break
    except httpx.RequestError as exc:
        yield {
            "type": "error",
            "reason": "runtime_error",
            "message": f"Ollama request failed: {exc}",
        }
        yield {"type": "message_stop", "usage": {}}
        return

    if assistant_text:
        fresh = chat_history.load_conversation(conversation_id, base=base)
        if fresh is not None:
            chat_history.append_message(
                fresh,
                role="assistant",
                content=[{"type": "text", "text": assistant_text}],
                base=base,
            )
