"""Unit tests for the Mixture-of-Agents aggregation (scripts/orchestrator/moa.py).

Method (b): union + cross-verify, recall-first. Pure logic, no LLM.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from orchestrator.moa import aggregate  # noqa: E402


def _f(pid, cls):
    return {"property_id": pid, "classification": cls, "detail": f"{pid}:{cls}"}


def test_single_flag_is_kept_recall_first():
    """One model flags, the others are neutral (not an explicit clear) -> kept."""
    out = aggregate({
        "m1": [_f("P1", "vulnerability")],
        "m2": [_f("P1", "informational")],
        "m3": [_f("P1", "inconclusive")],
    })
    assert len(out) == 1
    assert out[0]["classification"] == "vulnerability"
    assert out[0]["moa"]["decision"] == "kept-union"
    assert out[0]["moa"]["flagged_by"] == ["m1"]
    assert out[0]["moa"]["cleared_by"] == []


def test_flag_survives_single_clear():
    """1 flag + 1 clear + 1 neutral (n=3, majority=2): only 1 clear < 2 -> kept."""
    out = aggregate({
        "m1": [_f("P1", "vulnerability")],
        "m2": [_f("P1", "not-a-vulnerability")],
        "m3": [_f("P1", "informational")],
    })
    assert out[0]["moa"]["decision"] == "kept-union"
    assert out[0]["moa"]["cleared_by"] == ["m2"]


def test_majority_clear_downgrades_but_never_drops():
    """1 flag + 2 explicit clears (majority) -> demoted to inconclusive, kept."""
    out = aggregate({
        "m1": [_f("P1", "potential-vulnerability")],
        "m2": [_f("P1", "not-a-vulnerability")],
        "m3": [_f("P1", "safe")],
    })
    assert len(out) == 1, "a finding is never silently dropped"
    assert out[0]["classification"] == "inconclusive"
    assert out[0]["moa"]["decision"] == "outvoted-review"
    assert out[0]["moa"]["cleared_by"] == ["m2", "m3"]


def test_union_keeps_strongest_flag_as_canonical():
    """potential + full vulnerability -> canonical is the stronger one."""
    out = aggregate({
        "m1": [_f("P1", "potential-vulnerability")],
        "m2": [_f("P1", "vulnerability")],
        "m3": [_f("P1", "vulnerability")],
    })
    assert out[0]["classification"] == "vulnerability"
    assert out[0]["moa"]["flagged_by"] == ["m1", "m2", "m3"]


def test_no_flag_passes_consensus_clear_through():
    out = aggregate({
        "m1": [_f("P1", "not-a-vulnerability")],
        "m2": [_f("P1", "safe")],
        "m3": [_f("P1", "not-a-vulnerability")],
    })
    assert out[0]["moa"]["decision"] == "no-flag"
    assert out[0]["classification"] in ("not-a-vulnerability", "safe")


def test_multiple_properties_and_order_preserved():
    out = aggregate({
        "m1": [_f("P1", "safe"), _f("P2", "vulnerability")],
        "m2": [_f("P1", "safe"), _f("P2", "not-a-vulnerability")],
        "m3": [_f("P1", "safe"), _f("P2", "informational")],
    })
    assert [r["property_id"] for r in out] == ["P1", "P2"]
    assert out[0]["moa"]["decision"] == "no-flag"          # P1 all clear
    assert out[1]["moa"]["decision"] == "kept-union"       # P2 1 flag, 1 clear < majority


def test_property_only_one_model_saw():
    """n=1 for a property only one model returned: a flag is kept (majority=1,
    0 clears < 1)."""
    out = aggregate({
        "m1": [_f("P1", "vulnerability")],
        "m2": [],
        "m3": [],
    })
    assert out[0]["moa"]["decision"] == "kept-union"
    assert out[0]["moa"]["n_models"] == 1


def test_case_insensitive_classification():
    out = aggregate({"m1": [_f("P1", "Vulnerability")], "m2": [_f("P1", "SAFE")]})
    assert out[0]["moa"]["flagged_by"] == ["m1"]
    assert out[0]["moa"]["cleared_by"] == ["m2"]


# --- HermesMoARunner fan-out + fuse (mocked members, no LLM) ---

import asyncio  # noqa: E402
import types  # noqa: E402


def _make_runner():
    from orchestrator.hermes_moa_runner import HermesMoARunner
    cfg = types.SimpleNamespace(item_id_field="property_id", max_turns_per_batch=1)
    # avoid real CircuitBreaker(config) construction needs
    from orchestrator.runner import CircuitBreaker
    r = HermesMoARunner.__new__(HermesMoARunner)
    r.config = cfg
    r.circuit_breaker = None
    r.cost_tracker = None
    r.models = ["m1", "m2", "m3"]
    r.model = "m1+m2+m3"
    r.members = {}
    return r


def _member(results):
    class M:
        async def run_batch(self, batch, w, b):
            return results
    return M()


def test_runner_fuses_members_recall_first():
    r = _make_runner()
    r.members = {
        "m1": _member([_f("P1", "vulnerability")]),
        "m2": _member([_f("P1", "not-a-vulnerability")]),
        "m3": _member([_f("P1", "informational")]),
    }
    out = asyncio.run(r.run_batch([{"property_id": "P1"}], 0, 0))
    assert len(out) == 1
    assert out[0]["moa"]["decision"] == "kept-union"       # 1 flag, 1 clear < majority
    assert out[0]["moa"]["flagged_by"] == ["m1"]


def test_runner_survives_one_failing_member():
    r = _make_runner()
    class Boom:
        async def run_batch(self, *a):
            raise RuntimeError("proxy hiccup")
    r.members = {
        "m1": _member([_f("P1", "vulnerability")]),
        "m2": Boom(),
        "m3": _member([_f("P1", "safe")]),
    }
    out = asyncio.run(r.run_batch([{"property_id": "P1"}], 0, 0))
    # m2 dropped; m1 flag vs m3 clear, n=2 majority=1, 1 clear not < 1 -> outvoted-review
    assert len(out) == 1
    assert out[0]["moa"]["n_models"] == 2


def test_runner_all_members_fail_returns_none():
    r = _make_runner()
    class Boom:
        async def run_batch(self, *a):
            raise RuntimeError("down")
    r.members = {"m1": Boom(), "m2": Boom(), "m3": Boom()}
    assert asyncio.run(r.run_batch([{"property_id": "P1"}], 0, 0)) is None
