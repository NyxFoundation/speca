"""End-to-end: Phase 02c graph mode wires the deterministic resolver into the
orchestrator (speca#157). Runs the real Phase02cOrchestrator with
SPECA_02C_RESOLUTION=graph over a fixture workspace + 01e, asserting a
schema-valid 02c_PARTIAL is produced with NO LLM.

Needs the tree-sitter grammars: run via `uv run --with tree-sitter --with
tree-sitter-language-pack --with tree-sitter-c-sharp --with pytest -m pytest
tests/test_02c_graph_integration.py`.
"""
import asyncio
import glob
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter")
try:
    import tree_sitter_c_sharp  # noqa: F401
    import tree_sitter_language_pack  # noqa: F401
except Exception:
    pytest.skip("tree-sitter grammars unavailable", allow_module_level=True)

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT))

_BENCH_REPO = _ROOT / "scripts/orchestrator/graph_02c/fixtures/bench_repo"


def _prop(pid: str, covers: str) -> dict:
    return {
        "property_id": pid, "text": "t", "type": "invariant", "assertion": "x",
        "severity": "HIGH", "covers": covers,
        "reachability": {"classification": "external", "entry_points": ["P2P"],
                         "attacker_controlled": True, "bug_bounty_scope": "in_scope"},
        "bug_bounty_eligible": True, "exploitability": "high",
    }


def test_phase02c_graph_mode_resolves_without_llm(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    e01 = {"properties": [_prop("B-ATT", "process_attestation"), _prop("B-FC", "on_block")]}
    (out / "01e_PARTIAL_W0B0_1700000000.json").write_text(json.dumps(e01))

    monkeypatch.setenv("SPECA_OUTPUT_DIR", str(out))
    monkeypatch.setenv("SPECA_TARGET_WORKSPACE", str(_BENCH_REPO))
    monkeypatch.setenv("SPECA_02C_RESOLUTION", "graph")

    from orchestrator.base import Phase02cOrchestrator

    orch = Phase02cOrchestrator("02c")
    asyncio.run(orch.run())

    files = glob.glob(str(out / "02c_PARTIAL_*.json"))
    assert files, "graph mode produced no 02c_PARTIAL"
    props = []
    for f in files:
        props += json.load(open(f)).get("properties_with_code", [])
    by = {p["property_id"]: p for p in props}
    assert set(by) == {"B-ATT", "B-FC"}
    for pid, exp_symbol in [("B-ATT", "ProcessAttestation"), ("B-FC", "on_block")]:
        cs = by[pid]["code_scope"]
        assert cs["resolution_status"] == "resolved"
        locs = cs["locations"]
        assert any(l["symbol"] == exp_symbol for l in locs), (pid, locs)
        # schema-compatible line_range shape
        assert all("line_range" in l and "start" in l["line_range"] for l in locs)
