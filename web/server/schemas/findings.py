"""Pydantic schemas for the Findings API.

These models describe the *normalized* shape returned by the
``GET /api/runs/<id>/findings`` endpoints, as designed in
``docs/UI_DESIGN.md`` Section 7.4. Normalization itself lives in
:mod:`web.server.services.finding_normalizer`; this module only declares
the wire shape.

The schema is intentionally lenient on the boundary:

* ``verdict`` is kept as a free-form string. Phase 04 verdicts use a closed
  set (``CONFIRMED_VULNERABILITY`` etc.) but forks may add new ones, so we
  validate severity strictly and verdict softly. The frontend ``VerdictChip``
  decides how to render unknown verdicts.
* ``critique`` / ``related_past_fixes`` are placeholders for v3 (Phase 05).
  The keys are present so the frontend can rely on the field existing;
  v0 always returns ``None`` / ``[]``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Closed enums -----------------------------------------------------------------

Severity = Literal["Critical", "High", "Medium", "Low", "Informational"]
Phase = Literal["03", "04", "05"]


class Finding(BaseModel):
    """One normalized finding row.

    Phase 03 ``audit_items`` and Phase 04 ``reviewed_items`` are joined by
    ``property_id`` (see :mod:`web.server.services.finding_loader`). The
    flattened shape mirrors ``docs/UI_DESIGN.md`` Section 7.4 so the
    frontend can consume it without an additional normalization pass.
    """

    model_config = ConfigDict(extra="allow")

    run_id: str
    phase: Phase
    property_id: str
    # Target/client the finding belongs to (derived from the
    # ``outputs/<target>/`` subdirectory). ``None`` for the single-target
    # top-level ``outputs/`` layout. Backs the client filter added for #54.
    target: str | None = None
    severity: Severity
    # Phase 04 verdict (raw upstream string). Frontend decides display.
    verdict: str | None = None
    file: str | None = None
    line_range: str | None = None
    evidence_snippet: str | None = None
    proof_trace: str | None = None
    gates_passed: list[str] = Field(default_factory=list)
    reviewer_notes: str | None = None
    # v0 placeholders, present so frontend types stay stable across versions.
    related_past_fixes: list[str] = Field(default_factory=list)
    critique: dict | None = None


class FindingsMeta(BaseModel):
    """Envelope metadata for the list endpoint.

    ``data_source`` is the explicit v0 banner the frontend must show. When
    per-run isolation lands in v1, this becomes ``"run_scoped"`` and the
    banner is dropped.
    """

    model_config = ConfigDict(extra="forbid")

    data_source: Literal["current_outputs", "run_scoped"] = "current_outputs"
    count: int = 0
    # Distinct client/target names across the *unfiltered* finding set, so the
    # frontend can populate the client dropdown without a second request.
    targets: list[str] = Field(default_factory=list)


class FindingsResponse(BaseModel):
    """``GET /api/runs/<id>/findings`` response body."""

    model_config = ConfigDict(extra="forbid")

    data: list[Finding] = Field(default_factory=list)
    meta: FindingsMeta = Field(default_factory=FindingsMeta)


class FindingQuery(BaseModel):
    """Query string for the list endpoint.

    All fields are optional. ``severity`` is validated against the closed
    enum so a typo returns 422 rather than silently matching nothing.
    """

    model_config = ConfigDict(extra="forbid")

    phase: Literal["03", "04"] | None = None
    severity: Severity | None = None
    verdict: str | None = None
    target: str | None = None
