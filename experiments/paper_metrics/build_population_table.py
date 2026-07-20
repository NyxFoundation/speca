#!/usr/bin/env python3
"""RQ1 population-mapping table (issue #107): the single denominator source.

Builds the chain
  raw audit outputs -> positive findings -> adjudicated -> clusters -> GT-match
from Phase 03 (audit_items) and Phase 04 (reviewed_items) outputs. Counts that
the pipeline records are computed directly; the two steps the schema does NOT
capture (clustering and ground-truth matching) require external maps and are
reported as such rather than fabricated.

Grounded in scripts/orchestrator/schemas.py:
  - AuditMapItem.property_id, AuditMapItem.classification
  - ReviewedItem.property_id, ReviewedItem.review_verdict
AuditClassification positive set = {vulnerable, vulnerability, potential-vulnerability}.

Run on real data:
  python build_population_table.py --p03 outputs/03_PARTIAL_*.json \
      --p04 outputs/04_PARTIAL_*.json [--clusters clusters.json] [--gt gt_map.json]
Self-test (no data):
  python build_population_table.py --selftest
"""
from __future__ import annotations

import argparse
import glob
import json
import sys

POSITIVE = {"vulnerable", "vulnerability", "potential-vulnerability"}
EXCLUDED = {"not-a-vulnerability", "out-of-scope", "safe", "informational", "inconclusive"}


def _read(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def build(p03: list[dict], p04: list[dict], clusters: dict | None, gt: dict | None) -> dict:
    raw = 0
    positive_ids: list[str] = []
    excluded = 0
    for part in p03:
        for item in part.get("audit_items", []):
            raw += 1
            cls = str(item.get("classification", "")).strip().lower()
            if cls in POSITIVE:
                positive_ids.append(item.get("property_id", ""))
            elif cls in EXCLUDED:
                excluded += 1

    confirmed_ids: list[str] = []
    disputed = 0
    adjudicated = 0
    for part in p04:
        for item in part.get("reviewed_items", []):
            adjudicated += 1
            verdict = str(item.get("review_verdict", "")).strip()
            pid = item.get("property_id") or item.get("check_id") or ""
            if verdict == "Confirmed":
                confirmed_ids.append(pid)
            elif verdict == "Disputed":
                disputed += 1

    table = {
        "raw_audit_outputs": raw,
        "excluded_not_vuln_or_oos": excluded,
        "positive_findings": len(positive_ids),
        "adjudicated_reviewed": adjudicated,
        "confirmed": len(confirmed_ids),
        "disputed": disputed,
    }

    # Clusters and GT-match are NOT in the output schema -- require external maps.
    if clusters is not None:
        cl = {clusters.get(pid) for pid in confirmed_ids if clusters.get(pid)}
        table["clusters"] = len(cl)
    else:
        table["clusters"] = "REQUIRES --clusters (property_id -> cluster_id); not in schema"

    if gt is not None:
        matched = {gt.get(pid) for pid in confirmed_ids if gt.get(pid)}
        table["gt_match_findings"] = len([m for m in matched if m])
        table["gt_ids_covered"] = sorted(m for m in matched if m)
    else:
        table["gt_match_findings"] = "REQUIRES --gt (property_id -> gt_id); not in schema"

    table["chain"] = (
        f"{table['raw_audit_outputs']} raw -> {table['positive_findings']} positive "
        f"-> {table['adjudicated_reviewed']} adjudicated -> {table['clusters']} clusters "
        f"-> {table['gt_match_findings']} GT-match"
    )
    table["_note"] = (
        "raw/positive/adjudicated/confirmed/disputed computed from outputs. "
        "clusters and GT-match need external maps (not captured by the pipeline "
        "schema) -- this is the #103/#104 provenance gap; see paper_metrics/README.md."
    )
    return table


def _selftest() -> int:
    p03 = [{"audit_items": [
        {"property_id": "P1", "classification": "vulnerable"},
        {"property_id": "P2", "classification": "potential-vulnerability"},
        {"property_id": "P3", "classification": "not-a-vulnerability"},
        {"property_id": "P4", "classification": "out-of-scope"},
    ]}]
    p04 = [{"reviewed_items": [
        {"property_id": "P1", "review_verdict": "Confirmed"},
        {"property_id": "P2", "review_verdict": "Disputed"},
    ]}]
    clusters = {"P1": "C1"}
    gt = {"P1": "GT-7"}
    t = build(p03, p04, clusters, gt)
    assert t["raw_audit_outputs"] == 4, t
    assert t["excluded_not_vuln_or_oos"] == 2, t
    assert t["positive_findings"] == 2, t
    assert t["confirmed"] == 1 and t["disputed"] == 1, t
    assert t["clusters"] == 1, t
    assert t["gt_match_findings"] == 1 and t["gt_ids_covered"] == ["GT-7"], t
    # without external maps, those cells report the requirement
    t2 = build(p03, p04, None, None)
    assert "REQUIRES" in str(t2["clusters"]) and "REQUIRES" in str(t2["gt_match_findings"]), t2
    print("selftest OK")
    print(json.dumps(t, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="RQ1 population-mapping table (#107)")
    ap.add_argument("--p03", nargs="*", default=[], help="03 partial glob(s)")
    ap.add_argument("--p04", nargs="*", default=[], help="04 partial glob(s)")
    ap.add_argument("--clusters", help="JSON: property_id -> cluster_id")
    ap.add_argument("--gt", help="JSON: property_id -> ground-truth id")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    p03 = [_read(p) for g in args.p03 for p in glob.glob(g)]
    p04 = [_read(p) for g in args.p04 for p in glob.glob(g)]
    if not p03 or not p04:
        ap.error("provide --p03 and --p04 globs, or --selftest")
    clusters = _read(args.clusters) if args.clusters else None
    gt = _read(args.gt) if args.gt else None
    print(json.dumps(build(p03, p04, clusters, gt), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
