"""Pydantic models for the NDJSON pipeline events emitted by
``run_phase.py --json``.

These models are the **single source of truth** for the wire shape of every
event the orchestrator emits. The TypeScript CLI consumes JSON Schemas
generated from these classes (via ``scripts/export_schemas.py``) and
auto-derives a Zod parser, so a Pydantic-side rename surfaces as a CLI
build error rather than silent runtime drift.

See ``docs/SPECA_CLI_SPEC.md`` §8.2 / §12.1 for the event taxonomy.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class _EventBase(BaseModel):
    """Common envelope fields. ``ts`` is RFC 3339 UTC with millisecond precision.

    Subclasses pin ``type`` to a literal so the union narrows on the consumer
    side.
    """

    ts: str = Field(description="RFC 3339 UTC timestamp with millisecond precision.")


class PipelineStartedEvent(_EventBase):
    type: Literal["pipeline-started"] = "pipeline-started"
    phases: list[str]
    workers: int = Field(ge=0)
    max_concurrent: int = Field(ge=0)
    force: bool


class PhaseStartedEvent(_EventBase):
    type: Literal["phase-started"] = "phase-started"
    phase: str
    workers: int = Field(ge=0)
    max_concurrent: int = Field(ge=0)
    force: bool
    model: str | None = None


class PhaseCompletedEvent(_EventBase):
    type: Literal["phase-completed"] = "phase-completed"
    phase: str
    duration_s: float = Field(ge=0)
    total_results: int = Field(ge=0)


class PhaseFailedEvent(_EventBase):
    type: Literal["phase-failed"] = "phase-failed"
    phase: str
    reason: str
    duration_s: float = Field(ge=0)


class BudgetExceededEvent(_EventBase):
    type: Literal["budget-exceeded"] = "budget-exceeded"
    phase: str
    cost_usd: float | None = None
    max_budget_usd: float | None = None
    duration_s: float = Field(ge=0)


class CircuitBreakerTrippedEvent(_EventBase):
    type: Literal["circuit-breaker-tripped"] = "circuit-breaker-tripped"
    phase: str
    reason: str
    stats: dict[str, Any] = Field(default_factory=dict)
    duration_s: float = Field(ge=0)


class PipelineCompletedEvent(_EventBase):
    type: Literal["pipeline-completed"] = "pipeline-completed"
    phases: list[str]
    results: dict[str, bool]
    duration_s: float = Field(ge=0)


class WarningEvent(_EventBase):
    """Non-fatal degradation the user must see (issue #98).

    Example: a phase declares MCP servers that the resolved ``.mcp.json``
    does not provide — the pipeline keeps running, but the TUI dashboard
    (whose only inputs are this NDJSON stream and the log tail; orchestrator
    stderr is discarded in TUI mode) must surface the degradation.
    """

    type: Literal["warning"] = "warning"
    phase: str
    message: str


# Public union, helpful for ``isinstance`` checks and exhaustive matching on
# the Python side. The CLI does not import this; it uses the JSON Schemas.
PipelineEvent = (
    PipelineStartedEvent
    | PhaseStartedEvent
    | PhaseCompletedEvent
    | PhaseFailedEvent
    | BudgetExceededEvent
    | CircuitBreakerTrippedEvent
    | PipelineCompletedEvent
    | WarningEvent
)


__all__ = [
    "BudgetExceededEvent",
    "CircuitBreakerTrippedEvent",
    "PhaseCompletedEvent",
    "PhaseFailedEvent",
    "PhaseStartedEvent",
    "PipelineCompletedEvent",
    "PipelineEvent",
    "PipelineStartedEvent",
    "WarningEvent",
]
