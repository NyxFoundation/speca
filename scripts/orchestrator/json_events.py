"""NDJSON event emitter for ``run_phase.py --json``.

Emits one JSON object per line on stdout for pipeline-level transitions.
Consumers (TUI dashboards, CI scripts) read these events instead of
scraping decorative log output.

Wire shape: validated via the Pydantic models in
``orchestrator.event_models``. JSON Schemas exported from those models are
the language-neutral data contract the TypeScript CLI consumes.

See ``docs/SPECA_CLI_SPEC.md`` §8.2 / §12.1 for the event taxonomy.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import IO, Any

from pydantic import ValidationError

from .event_models import (
    BudgetExceededEvent,
    CircuitBreakerTrippedEvent,
    PhaseCompletedEvent,
    PhaseFailedEvent,
    PhaseStartedEvent,
    PipelineCompletedEvent,
    PipelineStartedEvent,
    WarningEvent,
)


# Map of public event-type strings to the Pydantic class that validates
# them. Adding a new event type means extending this map and
# ``event_models``; the JSON Schema export then picks the new class up
# automatically and the CLI Zod regeneration follows.
_TYPE_TO_MODEL: dict[str, Any] = {
    "pipeline-started": PipelineStartedEvent,
    "phase-started": PhaseStartedEvent,
    "phase-completed": PhaseCompletedEvent,
    "phase-failed": PhaseFailedEvent,
    "budget-exceeded": BudgetExceededEvent,
    "circuit-breaker-tripped": CircuitBreakerTrippedEvent,
    "pipeline-completed": PipelineCompletedEvent,
    "warning": WarningEvent,
}


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class JsonEventEmitter:
    """Emit pipeline events as NDJSON on a target stream.

    Stays a no-op when ``enabled=False`` so callers can wire it
    unconditionally and toggle behaviour from the CLI flag.

    ``emit`` keeps its kwargs-based signature for backwards compatibility,
    but every record is now routed through a Pydantic model that pins the
    wire shape; an unknown ``event_type`` or a malformed payload raises
    early instead of silently producing a record the CLI cannot parse.
    """

    def __init__(self, enabled: bool, stream: IO[str] | None = None) -> None:
        self.enabled = enabled
        # Capture the real stdout up-front. ``run_phase.py`` redirects
        # ``sys.stdout`` to stderr in --json mode to suppress decorative
        # output; capturing here keeps events going to the actual stdout.
        self._stream = stream if stream is not None else sys.__stdout__

    def emit(self, event_type: str, **payload: Any) -> None:
        if not self.enabled:
            return
        model_cls = _TYPE_TO_MODEL.get(event_type)
        if model_cls is None:
            raise ValueError(
                f"JsonEventEmitter.emit: unknown event_type {event_type!r}; "
                "add it to orchestrator.event_models and _TYPE_TO_MODEL."
            )
        try:
            event = model_cls(ts=payload.pop("ts", _now_ts()), **payload)
        except ValidationError as exc:
            raise ValueError(
                f"JsonEventEmitter.emit: payload for {event_type!r} fails "
                f"the contract — {exc.errors(include_url=False)}"
            ) from exc
        # ``exclude_none=False`` keeps explicit ``null`` fields on the wire
        # (e.g. ``cost_usd: null`` for the early-budget-exceeded path); the
        # CLI Zod schema accepts both null and number for those fields.
        line = event.model_dump_json(exclude_none=False)
        try:
            self._stream.write(line + "\n")
            self._stream.flush()
        except (BrokenPipeError, ValueError):
            # Consumer hung up or stream closed; let the orchestrator
            # finish and surface its own errors instead of crashing here.
            self.enabled = False


# ---------------------------------------------------------------------------
# Process-wide emitter registry.
#
# ``run_phase.py`` owns the JsonEventEmitter and threads it through the
# top-level pipeline functions, but deeply nested components (e.g.
# ``ClaudeRunner`` warning about missing MCP servers, issue #98) have no
# constructor path to it. They call ``get_active_emitter()`` instead:
# a disabled no-op instance is returned until ``run_phase.py`` registers the
# real one, so callers never need a None check and non-JSON runs stay silent
# on stdout. Single-process orchestration (workers are asyncio tasks), so a
# module-level slot is safe.
# ---------------------------------------------------------------------------

_active_emitter: JsonEventEmitter | None = None


def set_active_emitter(emitter: JsonEventEmitter) -> None:
    """Register the process-wide emitter (called once by ``run_phase.py``)."""
    global _active_emitter
    _active_emitter = emitter


def get_active_emitter() -> JsonEventEmitter:
    """Return the process-wide emitter, or a disabled no-op instance."""
    if _active_emitter is None:
        return JsonEventEmitter(enabled=False)
    return _active_emitter
