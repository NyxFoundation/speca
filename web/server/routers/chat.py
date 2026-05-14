"""HTTP / SSE routes for the Chat slice.

Three endpoints:

* ``GET /api/chat/conversations`` — sidebar list (newest first).
* ``GET /api/chat/conversations/{conversation_id}`` — full message log.
* ``POST /api/chat/conversations/{conversation_id}/messages`` — server-sent
  events streaming the model's response. Body: ``{"text": "..."}``.

The client mints the conversation UUID (matches the design doc — chat
history is per-project and the URL is the canonical identifier). The
``POST`` endpoint creates the file on first use.

The router stays thin; all heavy lifting is in
:mod:`web.server.services.chat_runtime` and :mod:`web.server.services.chat_history`.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from web.server.schemas.chat import (
    Conversation,
    ConversationSummary,
    PostMessageRequest,
    ToolApprovalRequest,
    ToolApprovalResponse,
)
from web.server.services import (
    chat_approvals,
    chat_history,
    chat_runtime_registry,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations_route() -> list[ConversationSummary]:
    """Return a list of stored conversations, newest first."""

    return chat_history.list_conversations()


@router.get(
    "/conversations/{conversation_id}",
    response_model=Conversation,
)
def get_conversation_route(conversation_id: str) -> Conversation:
    """Return the full message history for one conversation."""

    try:
        convo = chat_history.load_conversation(conversation_id)
    except ValueError as exc:
        # invalid id format — distinct from "not found" so the SPA can
        # show "bad URL" rather than "we deleted your history".
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if convo is None:
        raise HTTPException(
            status_code=404,
            detail=f"conversation not found: {conversation_id}",
        )
    return convo


@router.post("/conversations/{conversation_id}/messages")
async def post_message_route(
    conversation_id: str, body: PostMessageRequest
) -> EventSourceResponse:
    """Stream the model's response as SSE events.

    The conversation file is created on first POST. Each event is sent as
    a ``data:`` line whose JSON body matches the wire shape documented in
    ``docs/UI_DESIGN.md`` § 7.2.
    """

    try:
        # Validate the id eagerly so we return 400 before we open a stream.
        chat_history.ensure_conversation(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text must not be empty")

    # Runtime dispatch — the registry inspects RuntimePreferences and
    # picks between Anthropic SDK / claude CLI subprocess / codex CLI /
    # Ollama HTTP. The SPA wire shape is identical across runtimes.
    async def event_source() -> AsyncIterator[dict]:
        try:
            async for event in chat_runtime_registry.stream_response(
                conversation_id=conversation_id,
                user_text=text,
            ):
                yield {"data": json.dumps(event, ensure_ascii=False, default=str)}
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("chat: unexpected runtime error (%s)", exc)
            yield {
                "data": json.dumps(
                    {
                        "type": "error",
                        "reason": "runtime_error",
                        "message": str(exc),
                    }
                )
            }

    # ``EventSourceResponse`` from sse-starlette handles the
    # ``Content-Type: text/event-stream`` header, keep-alive pings, and
    # framing for us — we just yield dicts shaped ``{"data": "<json>"}``.
    return EventSourceResponse(event_source())


@router.post("/tool_approve", response_model=ToolApprovalResponse)
def tool_approve_route(body: ToolApprovalRequest) -> ToolApprovalResponse:
    """Approve, edit, or cancel a pending side-effect tool call.

    The body is delivered to the in-memory approval registry which
    unblocks the SSE stream that is currently suspended on this
    ``tool_call_id``. A 404 is returned if no pending approval exists —
    the most likely cause is that the stream already timed out, but it
    could also indicate a duplicate POST after the user clicked
    "approve" twice. Either way the SPA should refresh the chat to
    re-sync state.

    See ``docs/UI_DESIGN.md`` § 7.6 for the wire shape and Slice C1+C2
    handoff notes.
    """

    ok = chat_approvals.resolve(
        conversation_id=body.conversation_id,
        tool_call_id=body.tool_call_id,
        action=body.action,
        edited_input=body.edited_input,
    )
    if not ok:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "no_pending_approval",
                "tool_call_id": body.tool_call_id,
            },
        )
    return ToolApprovalResponse(ok=True)
