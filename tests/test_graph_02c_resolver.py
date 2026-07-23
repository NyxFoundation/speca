"""Step 2 tests: Tree-sitter symbol index + deterministic resolver (speca#157).

Runs against a tiny synthetic tree (no client clone). Requires the tree-sitter
grammars — run via `uv run --with tree-sitter --with tree-sitter-language-pack
--with tree-sitter-c-sharp -m pytest tests/test_graph_02c_resolver.py`.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

pytest.importorskip("tree_sitter")
try:
    import tree_sitter_c_sharp  # noqa: F401
    import tree_sitter_language_pack  # noqa: F401
except Exception:
    pytest.skip("tree-sitter grammars unavailable", allow_module_level=True)

from orchestrator.graph_02c.symbols import build_index  # noqa: E402
from orchestrator.graph_02c.resolver import resolve  # noqa: E402
from orchestrator.graph_02c.benchmark import GroundTruth  # noqa: E402
from orchestrator.graph_02c.metric import score_one, evaluate  # noqa: E402

_CS = """namespace Nethermind.Merge.Plugin.Data {
  public class ExecutionPayloadParams {
    public void ValidateParams(int count) {
      if (count < 0) { throw new System.Exception("bad"); }
      return;
    }
  }
}
"""

_GO = """package p
func ProcessAttestation(a int) int { return a + 1 }
type State struct { epoch int }
"""


def _tree(tmp_path, files):
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return build_index(tmp_path)


def test_index_extracts_symbols_polyglot(tmp_path):
    idx = _tree(tmp_path, {
        "Data/IExecutionPayloadParams.cs": _CS,
        "consensus/attestation.go": _GO,
    })
    names = {s.name for s in idx.symbols}
    assert "ValidateParams" in names and "ExecutionPayloadParams" in names
    assert "ProcessAttestation" in names and "State" in names


def test_resolver_high_confidence_on_spec_symbol(tmp_path):
    idx = _tree(tmp_path, {"Data/IExecutionPayloadParams.cs": _CS})
    prop = {"property_id": "P1", "spec_symbol": "ValidateParams",
            "text": "params must be validated", "assertion": "valid(params)"}
    r = resolve(prop, idx)
    assert r.confidence == "high"
    assert any(l["symbol"] == "ValidateParams" for l in r.code_scope["locations"])
    # and it matches the nethermind-style ground truth
    gt = GroundTruth("nethermind", "P1", "Data/IExecutionPayloadParams.cs",
                     "ExecutionPayloadParams.ValidateParams", 3, 6, "raw")
    assert score_one(gt, r.code_scope).hit is True


def test_resolver_low_confidence_triggers_fallback(tmp_path):
    idx = _tree(tmp_path, {"Data/IExecutionPayloadParams.cs": _CS})
    prop = {"property_id": "P2", "spec_symbol": "NonexistentThing",
            "text": "some abstract prose with no code identifiers here"}
    r = resolve(prop, idx)
    assert r.confidence == "low"          # -> the 02c phase falls back to the LLM
    assert r.code_scope["resolution_status"] == "not_found"


def test_resolver_medium_on_mined_token(tmp_path):
    idx = _tree(tmp_path, {"consensus/attestation.go": _GO})
    prop = {"property_id": "P3",
            "text": "the ProcessAttestation path must bound its work"}
    r = resolve(prop, idx)
    assert r.confidence == "medium"
    assert any(l["symbol"] == "ProcessAttestation" for l in r.code_scope["locations"])


def test_end_to_end_recall_on_synthetic_bench(tmp_path):
    idx = _tree(tmp_path, {"Data/IExecutionPayloadParams.cs": _CS,
                           "consensus/attestation.go": _GO})
    bench = [
        (GroundTruth("c", "P1", "Data/IExecutionPayloadParams.cs", "ValidateParams", 3, 6, "r"),
         {"property_id": "P1", "spec_symbol": "ValidateParams"}),
        (GroundTruth("c", "P3", "consensus/attestation.go", "ProcessAttestation", 2, 2, "r"),
         {"property_id": "P3", "spec_symbol": "ProcessAttestation"}),
    ]
    rep = evaluate([(gt, resolve(prop, idx).code_scope) for gt, prop in bench])
    assert rep.recall == 1.0


def test_name_extraction_return_type_vs_name(tmp_path):
    """Regression (#157): the method NAME, not the return type, is indexed —
    real nethermind pattern `public AcceptTxResult Accept(...)` + explicit
    interface impl `AcceptTxResult ITxFilter.Accept(...)` + Go `type X struct`."""
    idx = _tree(tmp_path, {
        "Filters/GasLimitTxFilter.cs":
            "namespace N { class GasLimitTxFilter {"
            " public AcceptTxResult Accept(Transaction tx) { return default; }"
            " AcceptTxResult ITxFilter.AcceptExplicit(Transaction tx) { return default; } } }",
        "consensus/state.go": "package p\ntype BeaconState struct { epoch int }\n",
    })
    names = {s.name for s in idx.symbols}
    assert "Accept" in names, "method name (not return type AcceptTxResult) must be indexed"
    assert "AcceptExplicit" in names, "explicit-interface method name must be indexed"
    assert "AcceptTxResult" not in names, "return type must NOT be indexed as a symbol"
    assert "BeaconState" in names, "Go type_declaration name (nested type_spec) must be indexed"


def test_run_02c_driver_gate_and_report(tmp_path):
    """Driver: high/medium accepted, low -> needs_llm_fallback (never dropped),
    report gives the fallback rate the CI accuracy gate asserts (#157 Step 3)."""
    from orchestrator.graph_02c.run import run_02c
    (tmp_path / "c").mkdir()
    (tmp_path / "c/attestation.go").write_text(
        "package p\nfunc ProcessAttestation(a int) int { return a }\n")
    props = [
        {"property_id": "P1", "covers": "ProcessAttestation"},      # high
        {"property_id": "P2", "text": "the ProcessAttestation call"},  # medium (mined)
        {"property_id": "P3", "covers": "NonExistentFunc",
         "text": "abstract prose no idents"},                        # low -> fallback
    ]
    items, rep = run_02c(tmp_path, props)
    # high-only accepted by default: P1(high) resolved; P2(medium) + P3(low) fall back
    assert rep.n == 3 and rep.resolved == 1 and rep.fallback == 2
    assert rep.by_confidence["high"] == 1 and rep.by_confidence["medium"] == 1
    byid = {i["property_id"]: i for i in items}
    assert byid["P1"]["x_02c_confidence"] == "high"
    assert byid["P1"]["code_scope"]["resolution_status"] == "resolved"
    assert byid["P2"]["code_scope"]["resolution_status"] == "needs_llm_fallback"
    assert byid["P3"]["code_scope"]["resolution_status"] == "needs_llm_fallback"
    # nothing dropped
    assert len(items) == len(props)


def test_cross_convention_seed_matching(tmp_path):
    """A pyspec snake_case `covers` matches client symbols regardless of the
    client's naming convention — Go camelCase and Rust snake_case (#157)."""
    idx = _tree(tmp_path, {
        "prysm/att.go": "package p\nfunc ProcessAttestation(a int) int { return a }\n",
        "lighthouse/att.rs": "fn process_attestation(a: i32) -> i32 { a }\n",
        "lodestar/att.ts": "function processAttestation(a: number): number { return a; }\n",
    })
    r = resolve({"property_id": "P", "covers": "process_attestation"}, idx)
    got = {l["symbol"] for l in r.code_scope["locations"]}
    assert r.confidence == "high"
    assert {"ProcessAttestation", "process_attestation", "processAttestation"} <= got


def test_nim_routine_symbol_extraction(tmp_path):
    """tree-sitter-nim models proc/func/method as a single `routine` node with
    the name in a `symbol` child — the index must extract it (#157 nimbus 0->OK)."""
    idx = _tree(tmp_path, {
        "beacon/epoch.nim":
            "proc process_justification_and_finalization*(state: var T) =\n"
            "  discard\n"
            "func getCurrentEpoch(state: T): Epoch =\n"
            "  discard\n",
    })
    names = {s.name for s in idx.symbols}
    assert "process_justification_and_finalization" in names
    assert "getCurrentEpoch" in names
    r = resolve({"property_id": "P", "covers": "process_justification_and_finalization"}, idx)
    assert r.confidence == "high"


def test_unique_prefix_match_on_strong_seed(tmp_path):
    """A client that adds a suffix (prysm ProcessJustificationAndFinalization
    PreCompute) resolves high via unique long-prefix match; ambiguous/short
    prefixes do NOT (#157 precision)."""
    idx = _tree(tmp_path, {
        "prysm/epoch.go":
            "package p\n"
            "func ProcessJustificationAndFinalizationPreCompute(a int) int { return a }\n",
    })
    r = resolve({"property_id": "P", "covers": "process_justification_and_finalization"}, idx)
    assert r.confidence == "high"
    assert any(l["symbol"] == "ProcessJustificationAndFinalizationPreCompute"
               for l in r.code_scope["locations"])

    # ambiguous: two divergent suffixes, neither a prefix of the other -> fallback
    idx2 = _tree(tmp_path, {
        "prysm/a.go": "package p\nfunc ProcessJustificationAndFinalizationPreCompute() {}\n",
        "prysm/b.go": "package p\nfunc ProcessJustificationAndFinalizationForkchoice() {}\n",
    })
    r2 = resolve({"property_id": "P", "covers": "process_justification_and_finalization"}, idx2)
    assert r2.confidence in ("medium", "low")

    # canonical + auto-generated wrapper (shortest is a prefix of the rest) -> high
    idx3 = _tree(tmp_path, {
        "prysm/a.go": "package p\nfunc ProcessJustificationAndFinalizationPreCompute() {}\n",
        "prysm/b.go": "package p\nfunc ProcessJustificationAndFinalizationPreComputeWrapper() {}\n",
    })
    r3 = resolve({"property_id": "P", "covers": "process_justification_and_finalization"}, idx3)
    assert r3.confidence == "high"
    assert any(l["symbol"] == "ProcessJustificationAndFinalizationPreCompute"
               for l in r3.code_scope["locations"])


def test_accuracy_gate_passes_on_bench_fixture():
    """Step 4: the CI accuracy gate runs on the vendored bench repo and passes
    strict thresholds (cross-convention pyspec->client resolution, #157)."""
    from orchestrator.graph_02c.eval_cli import run, _DEFAULT_REPO, _DEFAULT_BENCH
    res = run(_DEFAULT_REPO, _DEFAULT_BENCH)
    assert res["recall"] == 1.0
    assert res["fallback_rate"] == 0.0
    assert res["skipped_langs"] == []
    assert res["misses"] == []
