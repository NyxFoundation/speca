"""Load + merge Phase 03/04 PARTIAL JSON files into ``Finding`` records.

This is the Python sibling of ``cli/src/lib/findings/loader.ts``. The
contract differs slightly:

* The CLI uses the in-place CWD plus an arbitrary glob argument; the web
  backend always reads from :data:`web.server.config.SPECA_OUTPUTS_DIR`
  recursively (including subdirectories like ``outputs/test-litecoin/``).
* The CLI emits a flat-but-rich ``Finding`` (proof_trace, attack_scenario,
  classification, ...); the web backend emits the slimmer
  :class:`web.server.schemas.findings.Finding` matching ``UI_DESIGN.md``
  Section 7.4.
* Dedup policy differs: the CLI was "first-write wins, later phases
  override specific fields". The web v0 needs *Phase 04 wins over Phase 03*
  when both carry the same ``property_id``, with timestamp as tie-breaker.

v0 is intentionally a "global outputs/" reader. Per-run isolation
(per ``.speca/runs/<id>/outputs``) is v1 — until then the ``run_id`` path
param is accepted but ignored, and the response carries
``meta.data_source = "current_outputs"`` so the UI can banner the caveat.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal

from web.server.config import SPECA_OUTPUTS_DIR
from web.server.schemas.findings import Finding
from web.server.services.finding_normalizer import (
    extract_gates_passed,
    extract_locations,
    normalize_severity,
    normalize_verdict,
)

logger = logging.getLogger(__name__)


# A PARTIAL filename embeds the timestamp; we use it for dedup ordering when
# the file content's metadata.timestamp is missing or unparseable. Example:
#   03_PARTIAL_W0B0_1778105845.json -> 1778105845
_TIMESTAMP_RE = re.compile(r"_(?P<ts>\d{8,})\.json$")


@dataclass
class _PartialFinding:
    """Internal accumulator before we hand the merged record to Pydantic.

    Carries provenance (phase + timestamp + source file) so the dedup pass
    can pick the "winner" without re-reading the dict on each comparison.

    Phase 04 records only carry the verdict / adjusted severity / reviewer
    notes — the originating code path + proof trace lives in the Phase 03
    audit item. ``audit_raw`` keeps the Phase 03 view alongside the
    "winning" Phase 04 dict so :meth:`to_finding` can pull from either.
    """

    run_id: str
    phase: Literal["03", "04", "05"]
    property_id: str
    timestamp: int
    source_file: Path
    raw: dict[str, Any] = field(default_factory=dict)
    # Captured separately so a Phase 04 winner can still surface the
    # Phase 03 code_path / proof_trace.
    audit_raw: dict[str, Any] | None = None
    # Target/client the finding belongs to, derived from the PARTIAL file's
    # parent directory (``outputs/<target>/03_PARTIAL_*.json``). ``None`` for
    # top-level ``outputs/03_PARTIAL_*.json`` (single-target layout).
    target: str | None = None

    def to_finding(self) -> Finding:
        """Translate the accumulator into the wire ``Finding`` model.

        Field-by-field defaults follow the same priority as the TS loader:
        ``adjusted_severity`` beats Phase 03 implicit severity; verdict comes
        only from Phase 04; code path / proof trace comes from Phase 03.
        """

        raw = self.raw
        audit = self.audit_raw or (raw if self.phase == "03" else {})

        # Phase 04 emits adjusted_severity; Phase 03 has no explicit severity
        # so we fall back to whatever the upstream classifier set ("medium"
        # in some 01e outputs gets passed through).
        sev_raw = (
            raw.get("adjusted_severity")
            or raw.get("severity")
            or audit.get("severity")
            or raw.get("original_severity")
        )
        severity = normalize_severity(sev_raw)
        verdict = normalize_verdict(raw.get("review_verdict") or raw.get("verdict"))

        # Prefer Phase 03's code_scope / code_path when available — Phase 04
        # records never carry one.
        file_, line_range = (None, None)
        if audit:
            file_, line_range = extract_locations(audit)
        if file_ is None and line_range is None:
            file_, line_range = extract_locations(raw)

        # evidence_snippet: prefer an explicit snippet over the code-comment
        # like "code_snippet". Phase 03 sometimes carries this; Phase 04
        # never does.
        evidence = (
            raw.get("evidence_snippet")
            or raw.get("code_snippet")
            or (audit.get("evidence_snippet") if audit else None)
            or (audit.get("code_snippet") if audit else None)
        )

        proof_trace = raw.get("proof_trace") or (audit.get("proof_trace") if audit else None)
        reviewer_notes = raw.get("reviewer_notes")

        return Finding(
            run_id=self.run_id,
            phase=self.phase,
            property_id=self.property_id,
            target=self.target,
            severity=severity,
            verdict=verdict,
            file=file_,
            line_range=line_range,
            evidence_snippet=evidence if isinstance(evidence, str) and evidence else None,
            proof_trace=proof_trace or None,
            gates_passed=extract_gates_passed(raw),
            reviewer_notes=reviewer_notes or None,
            related_past_fixes=[],
            critique=None,
        )


def _extract_timestamp(path: Path, metadata: dict[str, Any] | None) -> int:
    """Pick the most reliable timestamp for dedup ordering.

    Prefers ``metadata.timestamp`` (the orchestrator's own clock at write
    time), falls back to the filename suffix, and finally to ``0`` so the
    record still participates in dedup (with "lowest priority").
    """

    if metadata:
        ts = metadata.get("timestamp")
        if isinstance(ts, int):
            return ts
        if isinstance(ts, str) and ts.isdigit():
            return int(ts)
    m = _TIMESTAMP_RE.search(path.name)
    if m:
        return int(m.group("ts"))
    return 0


def _iter_partial_files(outputs_dir: Path) -> Iterable[tuple[Path, str | None]]:
    """Yield ``(path, target)`` for Phase 03/04 PARTIALs under ``outputs/``.

    Uses two glob patterns:

    * top-level ``outputs/03_PARTIAL_*.json`` / ``04_PARTIAL_*.json`` —
      the single-target "current run" layout; ``target`` is ``None``.
    * one-level subdirs (``outputs/<target>/03_PARTIAL_*.json``) — the
      multi-target layout used by multi-client audits (e.g.
      ``outputs/lighthouse_fusaka/...``); ``target`` is the subdirectory
      name.

    The target is derived from *which glob pattern matched*, not from path
    comparison — so an ``outputs/`` that is itself a symlink cannot make a
    top-level PARTIAL masquerade as a target dir (or vice versa).

    Recursion is intentionally capped at one level to avoid pulling in
    ``outputs/logs/`` and ``outputs/graphs/`` — those don't contain PARTIAL
    files but a future ``**`` glob would still walk them.
    """

    if not outputs_dir.is_dir():
        return

    for phase in ("03", "04"):
        # Top-level outputs/<phase>_PARTIAL_*.json
        for path in outputs_dir.glob(f"{phase}_PARTIAL_*.json"):
            yield path, None
        # One subdirectory deep: outputs/<target>/<phase>_PARTIAL_*.json
        for path in outputs_dir.glob(f"*/{phase}_PARTIAL_*.json"):
            name = path.parent.name.strip()
            yield path, name or None


def _load_partial(path: Path) -> dict[str, Any] | None:
    """Read + JSON-parse one PARTIAL file. Returns ``None`` on any error.

    Errors are logged at WARNING. Lenient by design: a single malformed
    file must never abort the whole listing — partial results are
    first-class in SPECA's data model.
    """

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("findings.load: read failed for %s: %s", path, exc)
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("findings.load: JSON parse failed for %s: %s", path, exc)
        return None
    if not isinstance(parsed, dict):
        logger.warning("findings.load: top-level is not an object in %s", path)
        return None
    return parsed


def _ingest(
    partial: dict[str, Any],
    path: Path,
    run_id: str,
    accumulator: dict[tuple[str | None, str], _PartialFinding],
    target: str | None = None,
) -> None:
    """Merge one PARTIAL's items into the dedup accumulator.

    The accumulator is keyed on ``(target, property_id)`` — NOT property_id
    alone. Property ids are generated by Phase 01e from the *spec*
    (``{prefix}-{type}-{seq}``), so in a multi-client audit the same
    property_id legitimately appears in every client's outputs; keying on
    property_id alone would collapse those into one finding and silently
    drop clients.

    Within one ``(target, property_id)`` bucket, Phase 04 always wins over
    Phase 03. Within the same phase, the higher-timestamp record wins
    (covers the "rerun same batch" case where multiple files share a
    property_id).
    """

    metadata = partial.get("metadata") if isinstance(partial.get("metadata"), dict) else None
    timestamp = _extract_timestamp(path, metadata)
    declared_phase = None
    if metadata:
        raw_phase = metadata.get("phase")
        if isinstance(raw_phase, str):
            declared_phase = raw_phase

    for key, phase_default in (("audit_items", "03"), ("reviewed_items", "04")):
        items = partial.get(key)
        if not isinstance(items, list):
            continue
        # Trust metadata.phase when present, but fall back to the key name
        # so a half-populated metadata block still produces correct rows.
        phase = declared_phase if declared_phase in {"03", "04", "05"} else phase_default
        for item in items:
            if not isinstance(item, dict):
                continue
            property_id = item.get("property_id") or item.get("check_id")
            if not isinstance(property_id, str) or not property_id:
                continue

            candidate = _PartialFinding(
                run_id=run_id,
                phase=phase,  # type: ignore[arg-type]
                property_id=property_id,
                timestamp=timestamp,
                source_file=path,
                raw=item,
                audit_raw=item if phase == "03" else None,
                target=target,
            )

            key = (target, property_id)
            existing = accumulator.get(key)
            if existing is None:
                accumulator[key] = candidate
                continue
            # Phase priority: 05 > 04 > 03. Within the same phase, newer
            # timestamp wins. When Phase 04 supplants Phase 03 we carry over
            # the Phase 03 ``audit_raw`` so location / proof_trace survive.
            # (existing.target == candidate.target by construction — the
            # bucket key includes the target — so no target backfill is
            # needed here.)
            existing_rank = {"03": 0, "04": 1, "05": 2}.get(existing.phase, 0)
            candidate_rank = {"03": 0, "04": 1, "05": 2}.get(candidate.phase, 0)
            if candidate_rank > existing_rank:
                # Carry over the audit (Phase 03) raw if the loser had one.
                if candidate.audit_raw is None and existing.audit_raw is not None:
                    candidate.audit_raw = existing.audit_raw
                elif candidate.audit_raw is None and existing.phase == "03":
                    candidate.audit_raw = existing.raw
                accumulator[key] = candidate
            elif candidate_rank == existing_rank and candidate.timestamp > existing.timestamp:
                if candidate.audit_raw is None and existing.audit_raw is not None:
                    candidate.audit_raw = existing.audit_raw
                accumulator[key] = candidate
            elif candidate_rank < existing_rank:
                # The newcomer is lower-priority but might be the Phase 03
                # record that the existing Phase 04 winner is missing context
                # from. Backfill audit_raw without changing the winner.
                if existing.audit_raw is None and candidate.phase == "03":
                    existing.audit_raw = candidate.raw


def load_findings(run_id: str, outputs_dir: Path | None = None) -> list[Finding]:
    """Build the full deduped list of findings for one run.

    v0 ignores ``run_id`` for content but stamps it into each returned
    record. v1 will read ``.speca/runs/<run_id>/outputs/`` instead.
    """

    base = outputs_dir if outputs_dir is not None else SPECA_OUTPUTS_DIR
    accumulator: dict[tuple[str | None, str], _PartialFinding] = {}
    for path, target in _iter_partial_files(base):
        partial = _load_partial(path)
        if partial is None:
            continue
        _ingest(partial, path, run_id, accumulator, target=target)

    # Severity-sorted default. The frontend re-sorts but keeping a stable
    # server-side order makes the API easier to eyeball with curl.
    severity_rank = {
        "Critical": 0,
        "High": 1,
        "Medium": 2,
        "Low": 3,
        "Informational": 4,
    }

    findings = [acc.to_finding() for acc in accumulator.values()]
    findings.sort(
        key=lambda f: (
            severity_rank.get(f.severity, 99),
            f.property_id,
            f.target or "",
        )
    )
    return findings


def filter_findings(
    findings: list[Finding],
    *,
    phase: str | None = None,
    severity: str | None = None,
    verdict: str | None = None,
    target: str | None = None,
) -> list[Finding]:
    """In-memory filter to back ``GET /api/runs/<id>/findings?...``.

    All filters are exact-match — including ``target``, which matches the
    client/target directory name verbatim (no glob, no substring; glob
    matching on targets lives in the frontend ``repo:`` DSL key). Empty
    strings are treated like ``None`` so a frontend that forwards
    ``?severity=`` blank doesn't get a 422.
    """

    def keep(f: Finding) -> bool:
        if phase and f.phase != phase:
            return False
        if severity and f.severity != severity:
            return False
        if verdict and (f.verdict or "") != verdict:
            return False
        if target and (f.target or "") != target:
            return False
        return True

    return [f for f in findings if keep(f)]


def available_targets(findings: list[Finding]) -> list[str]:
    """Distinct, sorted list of targets/clients present in ``findings``.

    Backs the ``meta.targets`` field the client dropdown reads. Findings
    with no target (top-level ``outputs/`` single-target layout) contribute
    nothing, so a single-target run reports ``[]`` and the frontend simply
    hides the client filter.
    """

    return sorted({f.target for f in findings if f.target})


def find_finding(
    run_id: str,
    property_id: str,
    outputs_dir: Path | None = None,
    target: str | None = None,
) -> Finding | None:
    """Look up one finding by ``property_id`` (and, when given, ``target``).

    Property ids are spec-derived, so in a multi-client audit the same
    property_id exists once *per client* — a bare property_id lookup is
    ambiguous there. Callers coming from the list view should pass the
    row's ``target`` to pin the exact record. Without ``target`` the first
    match in the loader's stable order (severity, property_id, target)
    wins — correct for single-target runs, best-effort for multi-client.

    Falls through to :func:`load_findings` so the same dedup / phase
    priority logic applies. Acceptable for v0 because the lists are small
    (hundreds, not millions); v1 with per-run storage gets an index.
    """

    for f in load_findings(run_id, outputs_dir=outputs_dir):
        if f.property_id != property_id:
            continue
        # Empty string is treated like None (same as filter_findings) so a
        # frontend forwarding ``?target=`` blank still resolves the finding.
        if target and (f.target or "") != target:
            continue
        return f
    return None
