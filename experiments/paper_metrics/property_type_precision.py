#!/usr/bin/env python3
"""Per-property-type precision (issue #110, paper Table IX).

Joins Phase 01e properties (which carry `type` = invariant / precondition /
postcondition / assumption) to Phase 04 review verdicts (CONFIRMED_* = TP,
DISPUTED_FP = FP; see issue #132) by `property_id`, and reports TP/FP/precision per type plus the
overall precision with and without the `assumption` type (the gate #110 argues
for: report BOTH numbers, do not silently drop the 0%-precision type).

Grounded in scripts/orchestrator/schemas.py:
  - Property.property_id, Property.type
  - ReviewedItem.property_id, ReviewedItem.review_verdict (CONFIRMED_*/DISPUTED_FP)

Run on real data:
  python property_type_precision.py --e01e outputs/01e_PARTIAL_*.json \
      --p04 outputs/04_PARTIAL_*.json
Self-test (no data needed):
  python property_type_precision.py --selftest
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter, defaultdict

# Phase 04 review-verdict vocabulary (prompts/04_review_worker.md). See issue #132:
# the enum in schemas.py was stale ("Confirmed"/"Disputed"), so a plain equality
# check silently dropped every real verdict into "other" (TP=FP=0 on real data).
# TP = confirmed findings, FP = disputed findings. Legacy values are accepted too.
TP_VERDICTS = {"CONFIRMED_VULNERABILITY", "CONFIRMED_POTENTIAL", "Confirmed"}
FP_VERDICTS = {"DISPUTED_FP", "Disputed"}
# DOWNGRADED / NEEDS_MANUAL_REVIEW / PASS_THROUGH / NEEDS_MORE_INFO / "" fall to
# "other": excluded from precision and surfaced in the breakdown.
# DEFERRED DECISION (#107/#110): whether DOWNGRADED should count as a TP is a
# definitional choice for the paper authors; it is currently excluded, not folded in.


def load_property_types(e01e_paths: list[str]) -> dict[str, str]:
    """property_id -> type, from 01e partials."""
    types: dict[str, str] = {}
    for path in e01e_paths:
        data = json.loads(_read(path))
        for prop in data.get("properties", []):
            pid = prop.get("property_id")
            if pid:
                types[pid] = (prop.get("type") or "").strip().lower()
    return types


def load_verdicts(p04_paths: list[str]) -> list[tuple[str, str]]:
    """(property_id, verdict) pairs from 04 partials."""
    out: list[tuple[str, str]] = []
    for path in p04_paths:
        data = json.loads(_read(path))
        for item in data.get("reviewed_items", []):
            pid = item.get("property_id") or item.get("check_id") or ""
            verdict = str(item.get("review_verdict", "")).strip()
            if pid:
                out.append((pid, verdict))
    return out


def compute(types: dict[str, str], verdicts: list[tuple[str, str]]) -> dict:
    """Return per-type TP/FP/precision and overall (with/without assumption).

    TP = a verdict in TP_VERDICTS, FP = a verdict in FP_VERDICTS (issue #132).
    Items with any other verdict (DOWNGRADED / NEEDS_MANUAL_REVIEW / PASS_THROUGH
    / empty) are counted as "other" and excluded from precision, matching a strict
    TP/(TP+FP) definition. The raw distribution of the "other" verdicts is returned
    as other_breakdown so vocabulary drift is visible in the numbers, not silent."""
    per = defaultdict(lambda: {"TP": 0, "FP": 0, "other": 0, "N": 0})
    other_breakdown: Counter[str] = Counter()
    for pid, verdict in verdicts:
        ptype = types.get(pid, "unknown")
        cell = per[ptype]
        cell["N"] += 1
        if verdict in TP_VERDICTS:
            cell["TP"] += 1
        elif verdict in FP_VERDICTS:
            cell["FP"] += 1
        else:
            cell["other"] += 1
            other_breakdown[verdict or "<empty>"] += 1

    def prec(tp: int, fp: int) -> float | None:
        return round(tp / (tp + fp), 4) if (tp + fp) else None

    rows = {}
    for ptype, c in per.items():
        rows[ptype] = {**c, "precision": prec(c["TP"], c["FP"])}

    all_tp = sum(c["TP"] for c in per.values())
    all_fp = sum(c["FP"] for c in per.values())
    no_assume_tp = sum(c["TP"] for t, c in per.items() if t != "assumption")
    no_assume_fp = sum(c["FP"] for t, c in per.items() if t != "assumption")
    return {
        "per_type": rows,
        "other_breakdown": dict(other_breakdown),
        "overall_precision_incl_assumption": prec(all_tp, all_fp),
        "overall_precision_excl_assumption": prec(no_assume_tp, no_assume_fp),
        "report_template": (
            "assumption type precision = {a}; gated. Overall precision "
            "before/after gate = {b} -> {c}.".format(
                a=rows.get("assumption", {}).get("precision"),
                b=prec(all_tp, all_fp),
                c=prec(no_assume_tp, no_assume_fp),
            )
        ),
    }


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _selftest() -> int:
    # Uses the current Phase 04 vocabulary (issue #132) mixed with a legacy value
    # and a DOWNGRADED case that must land in "other" (not TP/FP):
    # 4 invariants (3 TP, 1 FP), 1 precondition TP, 1 postcondition FP,
    # 1 assumption FP -> assumption precision 0.0, overall changes on gate;
    # 1 extra invariant DOWNGRADED -> counted as other, precision unchanged.
    types = {
        "P1": "invariant", "P2": "invariant", "P3": "invariant", "P4": "invariant",
        "P5": "precondition", "P6": "postcondition", "P7": "assumption",
        "P8": "invariant",
    }
    verdicts = [
        ("P1", "CONFIRMED_VULNERABILITY"), ("P2", "CONFIRMED_POTENTIAL"),
        ("P3", "Confirmed"), ("P4", "DISPUTED_FP"),   # P3 exercises legacy alias
        ("P5", "CONFIRMED_VULNERABILITY"), ("P6", "DISPUTED_FP"), ("P7", "DISPUTED_FP"),
        ("P8", "DOWNGRADED"),
    ]
    r = compute(types, verdicts)
    assert r["per_type"]["assumption"]["precision"] == 0.0, r
    assert r["per_type"]["invariant"]["precision"] == 0.75, r  # 3 TP / (3 TP + 1 FP), DOWNGRADED excluded
    assert r["per_type"]["invariant"]["other"] == 1, r         # the DOWNGRADED item
    assert r["per_type"]["precondition"]["precision"] == 1.0, r
    # overall incl assumption: TP=4, FP=3 -> 0.5714; excl assumption TP=4 FP=2 -> 0.6667
    assert r["overall_precision_incl_assumption"] == 0.5714, r
    assert r["overall_precision_excl_assumption"] == 0.6667, r
    assert r["other_breakdown"] == {"DOWNGRADED": 1}, r
    print("selftest OK")
    print(json.dumps(r, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Per-property-type precision (#110)")
    ap.add_argument("--e01e", nargs="*", default=[], help="01e partial glob(s)")
    ap.add_argument("--p04", nargs="*", default=[], help="04 partial glob(s)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    e01e = [p for g in args.e01e for p in glob.glob(g)]
    p04 = [p for g in args.p04 for p in glob.glob(g)]
    if not e01e or not p04:
        ap.error("provide --e01e and --p04 globs, or --selftest")
    types = load_property_types(e01e)
    verdicts = load_verdicts(p04)
    print(json.dumps(compute(types, verdicts), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
