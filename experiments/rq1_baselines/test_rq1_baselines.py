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


def test_arm_a_units_from_real_scope_schema():
    # REAL BUG_BOUNTY_SCOPE.json shape (phase0_runner.py): top-level
    # in_scope_assets = flat list[str], plus in_scope_contracts = list[dict].
    scope = {
        "in_scope_assets": ["kzg/verify.go::VerifyBatch", "kzg/challenge.go"],
        "in_scope_contracts": [{"name": "Deposit", "address": "0xabc"}],
    }
    units = build_arm_a_units(scope)
    assert [u["check_id"] for u in units] == ["armA-001", "armA-002", "armA-003"], units
    for u in units:
        assert u["arm"] == "A_code_only"
        assert u["property_id"] == u["check_id"]          # surrogate id
        assert u["code_path"]                              # locates the asset
        assert "assertion" not in u and "type" not in u    # no typed-property signal
    assert units[2]["asset"] == "Deposit"                  # contract enumerated too
    print("ok: arm A units from real in_scope_assets schema")


def test_arm_a_dedups_and_empty_and_legacy_fallback():
    scope = {"in_scope_assets": ["a.go", "a.go", "b.go"]}
    assert len(build_arm_a_units(scope)) == 2              # dedup by asset
    assert build_arm_a_units({}) == []                     # empty -> empty (caller raises)
    # legacy fallback (older scope files) still yields units, not silent zero
    assert len(build_arm_a_units({"in_scope_components": ["x.go", "y.go"]})) == 2
    print("ok: arm A dedup/empty/legacy-fallback")


def test_build_arm_queue_reads_real_layout_and_refuses_empty():
    # Integration test of _build_arm_queue itself (the bug locus in the #156
    # review): scope file lives at <out_root>/BUG_BOUNTY_SCOPE.json (get_output_root
    # adds no `outputs/` subdir), and an empty queue must RAISE, not run silently.
    with tempfile.TemporaryDirectory() as td:
        out_root = Path(td) / "runs" / "A_code_only" / "run0"
        out_root.mkdir(parents=True)
        (out_root / "BUG_BOUNTY_SCOPE.json").write_text(
            json.dumps({"in_scope_assets": ["kzg/verify.go", "das/sampling.go"]}), encoding="utf-8")
        n = run_arms._build_arm_queue("A", out_root, td)
        assert n == 2, n
        q = json.loads((out_root / "03_ASYNC_QUEUE_W0B0.json").read_text())
        assert q["metadata"]["arm"] == "A_code_only" and len(q["items"]) == 2
        # empty scope must refuse, not build a 0-unit queue (spurious 0 recall)
        empty = Path(td) / "empty" / "run0"
        empty.mkdir(parents=True)
        (empty / "BUG_BOUNTY_SCOPE.json").write_text("{}", encoding="utf-8")
        try:
            run_arms._build_arm_queue("A", empty, td)
            assert False, "expected SystemExit on empty queue"
        except SystemExit:
            pass
    print("ok: _build_arm_queue real layout + refuses empty")


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
        # Real layout: Phase 04 outputs live directly under run_root (= SPECA_OUTPUT_DIR),
        # NOT under run_root/outputs — the #156 re-review bug this test now guards.
        run_root = Path(td)
        (run_root / "04_PARTIAL_x.json").write_text(json.dumps({"reviewed_items": [
            {"property_id": "armA-001", "review_verdict": "CONFIRMED_VULNERABILITY"},
            {"property_id": "armA-002", "review_verdict": "DISPUTED_FP"},        # only FP verdict
            {"property_id": "armA-003", "review_verdict": "CONFIRMED_POTENTIAL"},
            {"property_id": "armA-004", "review_verdict": "Confirmed"},          # legacy accepted
            {"property_id": "armA-005", "review_verdict": "DOWNGRADED"},         # gate-passing TP, counts for recall
        ]}), encoding="utf-8")
        ids = run_arms._confirmed_finding_ids(run_root)
        # DISPUTED_FP excluded; DOWNGRADED (severity-capped TP) INCLUDED for recall (#156)
        assert ids == {"armA-001", "armA-003", "armA-004", "armA-005"}, ids
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
