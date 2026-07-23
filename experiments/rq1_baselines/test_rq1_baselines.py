#!/usr/bin/env python3
"""Tests for the RQ1 controlled-baseline harness (issue #102): the queue builder
(arm A/B unit construction) and the scoring helpers. Self-contained, no compute /
no LLM — the parts that CAN be verified here. The Phase-03 queue-consumption
wiring (config.py registration) is validated by the smoke test on real compute,
not here.

Run: python experiments/rq1_baselines/test_rq1_baselines.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from queue_builder import build_arm_a_units, build_arm_b_units  # noqa: E402
import run_arms  # noqa: E402


def test_arm_a_units_cover_scope_no_property_signal():
    scope = {"in_scope": {"components": [
        {"name": "verify_batch", "path": "kzg/verify.go", "language": "Go"},
        {"name": "compute_challenge", "path": "kzg/challenge.go"},
    ]}}
    units = build_arm_a_units(scope)
    assert [u["check_id"] for u in units] == ["armA-001", "armA-002"], units
    # fairness: one unit per in-scope component, same population, no property fields
    assert len(units) == 2
    for u in units:
        assert u["arm"] == "A_code_only"
        assert u["property_id"] == u["check_id"]      # surrogate id
        assert u["code_path"]                          # locates code
        assert "assertion" not in u and "type" not in u  # no typed-property signal
    print("ok: arm A units")


def test_arm_a_dedups_and_handles_list_and_empty():
    scope = {"in_scope": [{"path": "a.go"}, {"path": "a.go"}, {"path": "b.go"}]}
    assert len(build_arm_a_units(scope)) == 2          # dedup by path
    assert build_arm_a_units({}) == []                 # empty scope -> empty (caller warns)
    print("ok: arm A dedup/empty")


def test_arm_b_units_carry_spec_provenance_not_properties():
    parts = [{"specs": [{"source_url": "https://eips/7594", "sub_graphs": [
        {"id": "SG-1", "name": "custody", "mermaid_file": "sg1.mmd", "invariants": ["nodes keep >= CUSTODY cols"]},
        {"id": "SG-2", "name": "sampling", "invariants": []},
    ]}]}]
    units = build_arm_b_units(parts)
    assert [u["check_id"] for u in units] == ["armB-001", "armB-002"], units
    u0 = units[0]
    assert u0["arm"] == "B_spec_only"
    assert u0["subgraph_id"] == "SG-1" and u0["source_url"].endswith("7594")
    # informal obligation provenance (so #103 can separate arm-B from arm-C), but
    # NOT a typed property (no assertion/type field)
    assert u0["obligation_hint"] == ["nodes keep >= CUSTODY cols"]
    assert "assertion" not in u0 and "type" not in u0
    print("ok: arm B units")


def test_confirmed_finding_ids_reads_phase04():
    with tempfile.TemporaryDirectory() as td:
        run_root = Path(td)
        (run_root / "outputs").mkdir()
        (run_root / "outputs" / "04_PARTIAL_x.json").write_text(json.dumps({"reviewed_items": [
            {"property_id": "armA-001", "review_verdict": "CONFIRMED_VULNERABILITY"},
            {"property_id": "armA-002", "review_verdict": "DISPUTED_FP"},
            {"property_id": "armA-003", "review_verdict": "CONFIRMED_POTENTIAL"},
            {"property_id": "armA-004", "review_verdict": "Confirmed"},   # legacy accepted
        ]}), encoding="utf-8")
        ids = run_arms._confirmed_finding_ids(run_root)
        assert ids == {"armA-001", "armA-003", "armA-004"}, ids   # DISPUTED excluded
    print("ok: confirmed finding ids from Phase 04")


def test_recovered_gt_and_property_only_set():
    f2g = {"armA-001": "H1", "armC-005": "H2", "armB-007": "M1"}
    assert run_arms._recovered_gt({"armA-001", "armX-999"}, f2g) == {"H1"}
    # decisive set logic: (B|C) minus A
    a, b, c = {"H1"}, {"M1"}, {"H2"}
    property_only = sorted((b | c) - a)
    assert property_only == ["H2", "M1"], property_only
    print("ok: recovered-gt + (B|C)-A")


def main() -> int:
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
