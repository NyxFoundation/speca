"""Mixture-of-Agents aggregation for the Hermes MoA runtime (speca#88 a/b/c-3).

Three independent models (via Hermes → ollama-cloud: deepseek-v4-pro,
qwen3.5, kimi-k2.7-code) each audit the same batch. This module fuses their
per-property classifications into one result set.

**Method (b) — union + cross-verify, recall-first** (matches Phase 04's
recall-safe design): take the union of what *any* model flagged, then keep a
flag unless a *majority* of the models that looked at it concretely cleared it.
We never drop a finding just because only one model raised it — that would
trade recall for precision. When a flag is out-voted we do NOT silently drop
it: it is downgraded to ``inconclusive`` and marked for review, so a real
finding is never lost, only demoted.

The module is pure (no I/O, no LLM); the runtime calls it with each model's
already-produced ``run_batch`` output. Every fused result carries an ``moa``
provenance block: which models flagged it, which cleared it, and the decision.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

# Phase 03 classification vocabulary (prompts/03_auditmap_worker_inline.md /
# schemas.Classification). A "flag" is a (potential) vulnerability; a "clear"
# is an explicit not-a-vulnerability / safe; everything else is neutral and
# neither flags nor refutes.
POSITIVE: frozenset[str] = frozenset(
    {"vulnerability", "vulnerable", "potential-vulnerability"}
)
CLEAR: frozenset[str] = frozenset({"safe", "not-a-vulnerability"})

# Strength order so the union keeps the strongest flag as canonical.
_STRENGTH = {"vulnerability": 3, "vulnerable": 3, "potential-vulnerability": 2}


def _classification(f: dict[str, Any]) -> str:
    return str(f.get("classification", "")).strip().lower()


def aggregate(
    per_model: dict[str, list[dict[str, Any]]],
    *,
    id_field: str = "property_id",
    positive: Iterable[str] = POSITIVE,
    clear: Iterable[str] = CLEAR,
) -> list[dict[str, Any]]:
    """Fuse per-model findings into one recall-first result set.

    ``per_model`` maps a model name to that model's ``run_batch`` output (a
    list of finding dicts, each carrying ``id_field`` and ``classification``).

    For each property audited by at least one model:

    * **flagged** by ≥1 model and **not** cleared by a majority → KEEP as a
      finding. Canonical record = the strongest flag; ``moa.decision =
      "kept-union"``.
    * flagged but a majority explicitly cleared it → DOWNGRADE to
      ``inconclusive`` (never dropped), ``moa.decision = "outvoted-review"``.
    * no model flagged it → the consensus clear/neutral result passes through,
      ``moa.decision = "no-flag"``.

    Every result gains an ``moa`` block: ``flagged_by`` / ``cleared_by`` /
    ``n_models`` / ``decision``.
    """
    positive = frozenset(x.lower() for x in positive)
    clear = frozenset(x.lower() for x in clear)

    by_prop: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    order: list[str] = []
    for model, findings in per_model.items():
        for f in findings or []:
            pid = str(f.get(id_field, ""))
            if pid not in by_prop:
                order.append(pid)
            by_prop[pid].append((model, f))

    fused: list[dict[str, Any]] = []
    for pid in order:
        votes = by_prop[pid]
        n = len(votes)
        flaggers = [(m, f) for m, f in votes if _classification(f) in positive]
        clearers = [m for m, f in votes if _classification(f) in clear]
        majority = (n + 1) // 2  # >half of the models that looked at it

        if flaggers and len(clearers) < majority:
            m, f = max(
                flaggers, key=lambda mf: _STRENGTH.get(_classification(mf[1]), 1)
            )
            record = dict(f)
            decision = "kept-union"
        elif flaggers:  # out-voted by a majority clear — demote, never drop
            _, f = flaggers[0]
            record = dict(f)
            record["classification"] = "inconclusive"
            decision = "outvoted-review"
        else:  # nobody flagged it
            _, f = votes[0]
            record = dict(f)
            decision = "no-flag"

        record["moa"] = {
            "flagged_by": sorted(m for m, _ in flaggers),
            "cleared_by": sorted(clearers),
            "n_models": n,
            "decision": decision,
        }
        fused.append(record)
    return fused
