"""Regression tests for additive provenance passthrough (speca#88 / speca#92).

The Lean property provider attaches additive fields (``lean_status``,
``lean_artifact``, ``kurtosis_test``) to Phase 01e properties. Workers in
later phases never receive those fields (``context_fields`` strips them)
and therefore never echo them, and Phase 02c's ``output_fields`` compaction
used to strip them from the saved PARTIAL — so the fields were 100% lost
at the 01e→02c boundary and never reached Phase 04, where the Kurtosis
verification backend (speca#92) needs to read ``kurtosis_test``.

These tests drive the real orchestrators end-to-end (02c → 03 → 04) over
real PARTIAL files in a temporary output root, with only the LLM runner
faked. The fake runner deliberately emits worker-shaped results *without*
the lean fields, so the tests prove the orchestrator itself carries the
fields across each phase — not that a mock echoed them.
"""

import asyncio
import glob
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add workspace root to sys.path
_WORKSPACE_ROOT = str(Path(__file__).resolve().parent.parent)
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from scripts.orchestrator.base import (
    Phase02cOrchestrator,
    Phase03Orchestrator,
    Phase04Orchestrator,
)
from scripts.orchestrator.collector import ResultCollector
from scripts.orchestrator.config import (
    LEAN_PROVENANCE_FIELDS,
    PHASE_CONFIGS,
    get_phase_config,
)


LEAN_FIELDS = {
    "lean_status": "proved",
    "lean_artifact": "NyxFoundation/gasper-lean4@main:Core/AccountableSafety.lean#k_safety",
    "kurtosis_test": "outputs/kurtosis/PROP-lean-001/assertion.scaffold.json",
}


def _lean_property(prop_id: str, severity: str = "Critical") -> dict:
    """A 01e property as the lean provider emits it (additive fields set)."""
    prop = {
        "property_id": prop_id,
        "text": f"Property {prop_id}",
        "type": "invariant",
        "assertion": "forall b, justified(b) -> valid(b)",
        "severity": severity,
        "covers": "FN-001",
        "reachability": {
            "classification": "reachable",
            "entry_points": ["p2p"],
            "attacker_controlled": True,
            "bug_bounty_scope": "in-scope",
        },
        "exploitability": "high",
        "bug_bounty_eligible": True,
    }
    prop.update(LEAN_FIELDS)
    prop["kurtosis_test"] = f"outputs/kurtosis/{prop_id}/assertion.scaffold.json"
    return prop


class _FakeRunner:
    """Stands in for ClaudeRunner. Emits worker-shaped results that do NOT
    contain the lean fields (a real worker never sees them), plus one junk
    field to prove output_fields compaction still works."""

    def __init__(self, config, semaphore, **kwargs):
        self.config = config

    async def run_batch(self, batch, worker_id, batch_index):
        phase = self.config.phase_id
        results = []
        for item in batch:
            pid = item.get("property_id", "")
            if phase == "02c":
                results.append({
                    "property_id": pid,
                    "text": item.get("text", ""),
                    "type": item.get("type", ""),
                    "assertion": item.get("assertion", ""),
                    "severity": item.get("severity", ""),
                    "covers": item.get("covers", ""),
                    "reachability": item.get("reachability", {}),
                    "exploitability": item.get("exploitability", ""),
                    "code_scope": {
                        "resolution_status": "resolved",
                        "files": ["core/state.py"],
                    },
                    "code_excerpt": "def apply_block(): ...",
                    # Junk the compaction must strip:
                    "worker_invented_field": "junk",
                    # Fabricated collision the upstream value must overwrite:
                    "lean_status": "FABRICATED-BY-WORKER",
                })
            elif phase == "03":
                # PROP-lean-002 exercises Phase 04's early-exit
                # (PASS_THROUGH) branch; the rest go to the 04 worker.
                classification = (
                    "not-a-vulnerability" if pid == "PROP-lean-002"
                    else "vulnerability"
                )
                results.append({
                    "property_id": pid,
                    "check_id": pid,
                    "classification": classification,
                    "severity": item.get("severity", ""),
                    "summary": "Fake audit finding.",
                    "code_scope": item.get("code_scope", {}),
                    "bug_bounty_eligible": True,
                })
            elif phase == "04":
                results.append({
                    "property_id": pid,
                    "review_verdict": "CONFIRMED_VULNERABILITY",
                    "original_classification": "vulnerability",
                    "adjusted_severity": "Critical",
                    "reviewer_notes": "Fake review.",
                    "spec_reference": "",
                })
        return results


@pytest.fixture()
def pipeline_env(tmp_path, monkeypatch):
    """Temp output root seeded with a lean-provider 01e PARTIAL + phase-0 files."""
    out = tmp_path / "outputs"
    out.mkdir()
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(out))
    monkeypatch.delenv("FORCE_EXECUTE", raising=False)

    properties = [
        _lean_property("PROP-lean-001", "Critical"),
        _lean_property("PROP-lean-002", "High"),
        # Severity-gated at 02c (min_severity=Low drops Informational):
        _lean_property("PROP-lean-003", "Informational"),
    ]
    (out / "01e_PARTIAL_W0B0_1.json").write_text(
        json.dumps({"properties": properties, "metadata": {"phase": "01e"}}),
        encoding="utf-8",
    )
    (out / "BUG_BOUNTY_SCOPE.json").write_text(
        json.dumps({"program": "test", "in_scope": ["core"]}), encoding="utf-8"
    )
    (out / "TARGET_INFO.json").write_text(
        json.dumps({"repo": "example/repo", "commit": "deadbeef"}), encoding="utf-8"
    )
    return out


def _run_phase(orchestrator):
    """Run a phase with the LLM runner faked out."""
    with patch("scripts.orchestrator.base.ClaudeRunner", _FakeRunner), \
         patch("scripts.orchestrator.runtime_registry.resolve_active",
               return_value="claude"):
        asyncio.run(orchestrator.run())


def _load_records(out_dir, pattern, key):
    records = []
    for fp in sorted(glob.glob(str(out_dir / pattern))):
        with open(fp, encoding="utf-8") as f:
            records.extend(json.load(f).get(key, []))
    return records


# ---------------------------------------------------------------------------
# Config-level guarantees
# ---------------------------------------------------------------------------

def test_lean_fields_declared_passthrough_for_02c_03_04():
    for phase in ("02c", "03", "04"):
        for field in LEAN_PROVENANCE_FIELDS:
            assert field in PHASE_CONFIGS[phase].passthrough_fields, (
                f"phase {phase} must carry {field}"
            )


def test_collector_output_filter_exempts_passthrough_fields(tmp_path, monkeypatch):
    """output_fields compaction keeps passthrough fields but still strips junk."""
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(tmp_path))
    config = get_phase_config("02c").model_copy(deep=True)
    assert config.output_fields, "test requires active compaction"
    collector = ResultCollector(config)
    record = {
        "property_id": "PROP-X",
        "text": "t",
        "worker_invented_field": "junk",
        **LEAN_FIELDS,
    }
    path = collector.save_partial([record], 0, 0)
    saved = json.loads(path.read_text(encoding="utf-8"))["properties_with_code"][0]
    for field, value in LEAN_FIELDS.items():
        assert saved[field] == value
    assert "worker_invented_field" not in saved, (
        "compaction must still strip worker-invented fields"
    )


# ---------------------------------------------------------------------------
# Pipeline survival: 01e -> 02c -> 03 -> 04 over real PARTIAL files
# ---------------------------------------------------------------------------

def test_lean_fields_survive_full_pipeline(pipeline_env):
    out = pipeline_env

    # ---- 02c ----
    orch_02c = Phase02cOrchestrator("02c", num_workers=1, max_concurrent=1)
    _run_phase(orch_02c)

    props = _load_records(out, "02c_PARTIAL_*.json", "properties_with_code")
    by_id = {p.get("property_id"): p for p in props}
    assert set(by_id) == {"PROP-lean-001", "PROP-lean-002", "PROP-lean-003"}

    for pid in ("PROP-lean-001", "PROP-lean-002"):
        prop = by_id[pid]
        assert prop["lean_status"] == "proved", (
            f"02c dropped/overwrote lean_status for {pid}"
        )
        assert prop["lean_artifact"] == LEAN_FIELDS["lean_artifact"]
        assert prop["kurtosis_test"] == (
            f"outputs/kurtosis/{pid}/assertion.scaffold.json"
        )
        assert "worker_invented_field" not in prop, (
            "02c compaction regressed: worker junk leaked into PARTIAL"
        )

    # Severity-gated early exit keeps provenance too. (Compaction strips
    # the "skipped" marker — pre-existing behavior; Phase 03 keys its own
    # early exit on code_scope.resolution_status.)
    gated = by_id["PROP-lean-003"]
    assert gated["code_scope"]["resolution_status"] == "out_of_scope"
    assert gated["kurtosis_test"] == (
        "outputs/kurtosis/PROP-lean-003/assertion.scaffold.json"
    )

    # ---- 03 ----
    orch_03 = Phase03Orchestrator(num_workers=1, max_concurrent=1)
    _run_phase(orch_03)

    audit_items = _load_records(out, "03_PARTIAL_*.json", "audit_items")
    audited = {
        a["property_id"]: a for a in audit_items
        if a.get("classification") in ("vulnerability", "not-a-vulnerability")
    }
    assert set(audited) == {"PROP-lean-001", "PROP-lean-002"}
    assert audited["PROP-lean-002"]["classification"] == "not-a-vulnerability"
    for pid, item in audited.items():
        assert item["lean_status"] == "proved", f"03 dropped lean_status for {pid}"
        assert item["kurtosis_test"] == (
            f"outputs/kurtosis/{pid}/assertion.scaffold.json"
        ), f"03 dropped kurtosis_test for {pid}"

    # ---- 04 ----
    orch_04 = Phase04Orchestrator("04", num_workers=1, max_concurrent=1)
    _run_phase(orch_04)

    reviewed = _load_records(out, "04_PARTIAL_*.json", "reviewed_items")
    by_verdict = {r["property_id"]: r for r in reviewed}
    assert by_verdict["PROP-lean-001"]["review_verdict"] == (
        "CONFIRMED_VULNERABILITY"
    )
    # Phase 04 early-exit (PASS_THROUGH) branch must keep provenance too.
    assert by_verdict["PROP-lean-002"]["review_verdict"] == "PASS_THROUGH"
    for pid in ("PROP-lean-001", "PROP-lean-002"):
        rec = by_verdict[pid]
        assert rec["lean_status"] == "proved", f"04 dropped lean_status for {pid}"
        assert rec["lean_artifact"] == LEAN_FIELDS["lean_artifact"]
        assert rec["kurtosis_test"] == (
            f"outputs/kurtosis/{pid}/assertion.scaffold.json"
        ), f"04 dropped kurtosis_test for {pid}"

    # The speca#92 consumption point: Phase 04 hands self.results to the
    # verification backend. kurtosis_test must be present there.
    backend_view = [
        r for r in orch_04.results
        if r.get("review_verdict") == "CONFIRMED_VULNERABILITY"
    ]
    assert backend_view, "no confirmed findings reached the backend view"
    for rec in backend_view:
        assert rec.get("kurtosis_test"), (
            "kurtosis_test missing from Phase 04 results — speca#92 backend "
            "cannot locate the fixture"
        )


def test_worker_fabricated_lean_value_is_overwritten(pipeline_env):
    """The fake 02c worker emits lean_status='FABRICATED-BY-WORKER'; the
    deterministic upstream value must win in the saved PARTIAL."""
    out = pipeline_env
    orch = Phase02cOrchestrator("02c", num_workers=1, max_concurrent=1)
    _run_phase(orch)

    props = _load_records(out, "02c_PARTIAL_*.json", "properties_with_code")
    processed = [p for p in props if not p.get("skipped")]
    assert processed
    for prop in processed:
        assert prop["lean_status"] == "proved", (
            "worker-fabricated lean_status leaked into the PARTIAL"
        )


def test_prompt_path_without_lean_fields_is_unchanged(tmp_path, monkeypatch):
    """Properties lacking the lean fields (prompt-path 01e) pass 02c exactly
    as before: no lean keys are invented, compaction still applies."""
    out = tmp_path / "outputs"
    out.mkdir()
    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(out))
    monkeypatch.delenv("FORCE_EXECUTE", raising=False)

    prop = _lean_property("PROP-prompt-001", "High")
    for field in LEAN_FIELDS:
        prop.pop(field, None)
    (out / "01e_PARTIAL_W0B0_1.json").write_text(
        json.dumps({"properties": [prop], "metadata": {}}), encoding="utf-8"
    )
    (out / "BUG_BOUNTY_SCOPE.json").write_text(
        json.dumps({"program": "test"}), encoding="utf-8"
    )

    orch = Phase02cOrchestrator("02c", num_workers=1, max_concurrent=1)
    _run_phase(orch)

    props = _load_records(out, "02c_PARTIAL_*.json", "properties_with_code")
    assert len(props) == 1
    saved = props[0]
    assert "worker_invented_field" not in saved
    assert "lean_artifact" not in saved
    assert "kurtosis_test" not in saved
    # The fake worker fabricates lean_status; with no upstream source the
    # orchestrator must drop it — passthrough names are trusted only when
    # the upstream input item provided them.
    assert "lean_status" not in saved, (
        "worker-fabricated lean_status must not survive without an "
        "upstream source"
    )
