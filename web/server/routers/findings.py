"""HTTP routes for the Findings API.

Two endpoints:

* ``GET /api/runs/<run_id>/findings`` — list, with optional
  ``?phase=&severity=&verdict=`` filters.
* ``GET /api/runs/<run_id>/findings/<property_id>`` — single record or 404.

v0 reads from the global ``outputs/`` directory (see
``finding_loader.load_findings``) and stamps ``meta.data_source =
"current_outputs"`` so the SPA can render an explanatory banner. Per-run
isolation arrives in v1.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from web.server.schemas.findings import (
    FindingsMeta,
    FindingsResponse,
    Finding,
)
from web.server.services.finding_loader import (
    available_targets,
    filter_findings,
    find_finding,
    load_findings,
)

router = APIRouter(prefix="/api", tags=["findings"])


@router.get("/runs/{run_id}/findings", response_model=FindingsResponse)
def list_findings(
    run_id: str,
    phase: Literal["03", "04"] | None = Query(default=None),
    severity: Literal["Critical", "High", "Medium", "Low", "Informational"] | None = Query(default=None),
    verdict: str | None = Query(default=None),
    target: str | None = Query(default=None),
) -> FindingsResponse:
    """Return the filtered finding list for one run.

    Query params are optional. ``severity`` is validated against the closed
    enum (FastAPI returns 422 on a typo). ``verdict`` / ``target`` are free
    text because forks may introduce new verdicts and target/client names
    are arbitrary directory names — the loader matches exactly against the
    raw upstream string.

    ``meta.targets`` always reflects the *unfiltered* client set so the
    dropdown keeps every client selectable even after one is chosen.
    """

    findings: list[Finding] = load_findings(run_id)
    targets = available_targets(findings)
    filtered = filter_findings(
        findings,
        phase=phase,
        severity=severity,
        verdict=verdict,
        target=target,
    )
    return FindingsResponse(
        data=filtered,
        meta=FindingsMeta(
            data_source="current_outputs",
            count=len(filtered),
            targets=targets,
        ),
    )


@router.get("/runs/{run_id}/findings/{property_id}", response_model=Finding)
def get_finding(
    run_id: str,
    property_id: str,
    target: str | None = Query(default=None),
) -> Finding:
    """Return one finding or raise 404.

    Property ids are spec-derived and repeat across clients in a
    multi-client audit, so the detail lookup accepts ``?target=<client>``
    to pin the exact record. The SPA's list rows link here with the row's
    own target. Without ``target`` the first match in the loader's stable
    order is returned (fine for single-target runs).

    Slice G will hit this endpoint when the SPA's detail page mounts;
    by returning the same normalized shape as the list endpoint the
    ``data-testid="finding-code-path"`` row stays stable.
    """

    finding = find_finding(run_id, property_id, target=target)
    if finding is None:
        raise HTTPException(status_code=404, detail=f"Finding {property_id} not found in run {run_id}")
    return finding
