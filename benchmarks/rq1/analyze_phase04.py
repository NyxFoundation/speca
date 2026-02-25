#!/usr/bin/env python3
"""Phase 04 FP/FN analysis — cross-reference Phase 04 verdicts with benchmark labels.

Reads:
  - Phase 04 PARTIAL files (outputs/04_PARTIAL_*.json)
  - Benchmark labels (findings_labels.csv)

Outputs:
  - Confusion matrix: Phase 04 verdict × benchmark auto_label
  - False negative detection (real findings disputed by Phase 04)
  - False positive retention (invalid findings confirmed by Phase 04)
  - Coverage stats (how many findings Phase 04 has processed)
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


# Phase 04 verdicts that reject findings
REJECT_VERDICTS = {"DISPUTED_FP"}
# Phase 04 verdicts that accept findings
ACCEPT_VERDICTS = {"CONFIRMED_VULNERABILITY", "CONFIRMED_POTENTIAL", "DOWNGRADED"}
# Benchmark labels considered true positives
TP_LABELS = {"tp", "tp_info", "fixed", "partially_fixed"}
# Benchmark labels considered false positives
FP_LABELS = {"fp_invalid"}


def load_phase04_verdicts(partials_pattern: str = "outputs/04_PARTIAL_*.json") -> dict[str, dict]:
    """Load all Phase 04 reviewed items → {property_id: verdict_data}."""
    verdicts: dict[str, dict] = {}
    for path in sorted(Path(".").glob(partials_pattern)):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[phase04] warning: skipping {path}: {e}")
            continue
        for item in data.get("reviewed_items", []):
            pid = item.get("property_id", "")
            if pid:
                verdicts[pid] = {
                    "verdict": item.get("review_verdict", ""),
                    "adjusted_severity": item.get("adjusted_severity", ""),
                    "original_classification": item.get("original_classification", ""),
                    "reviewer_notes": item.get("reviewer_notes", ""),
                    "source_file": str(path),
                }
    return verdicts


def load_benchmark_labels(csv_path: str | Path) -> list[dict]:
    """Load findings_labels.csv → list of row dicts."""
    rows: list[dict] = []
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def analyze(
    verdicts: dict[str, dict],
    labels: list[dict],
) -> dict:
    """Cross-reference Phase 04 verdicts with benchmark labels."""
    total_findings = len(labels)
    processed = 0
    unprocessed = 0

    # Confusion matrix: (verdict, benchmark_label) → count
    confusion: dict[tuple[str, str], int] = Counter()
    false_negatives: list[dict] = []
    false_positive_retained: list[dict] = []

    for row in labels:
        fid = row["finding_id"]
        auto_label = row.get("auto_label", "")

        if fid in verdicts:
            processed += 1
            v = verdicts[fid]
            verdict = v["verdict"]
            confusion[(verdict, auto_label)] += 1

            # FN: Phase 04 rejected a real finding
            if verdict in REJECT_VERDICTS and auto_label in TP_LABELS:
                false_negatives.append({
                    "finding_id": fid,
                    "repo": row.get("repo", ""),
                    "benchmark_label": auto_label,
                    "csv_severity": row.get("csv_severity", ""),
                    "csv_issue_id": row.get("csv_issue_id", ""),
                    "csv_title": row.get("csv_title", ""),
                    "phase04_verdict": verdict,
                    "adjusted_severity": v["adjusted_severity"],
                    "reviewer_notes": v["reviewer_notes"][:200],
                })

            # FP retained: Phase 04 accepted an invalid finding
            if verdict in ACCEPT_VERDICTS and auto_label in FP_LABELS:
                false_positive_retained.append({
                    "finding_id": fid,
                    "repo": row.get("repo", ""),
                    "benchmark_label": auto_label,
                    "csv_issue_id": row.get("csv_issue_id", ""),
                    "csv_title": row.get("csv_title", ""),
                    "phase04_verdict": verdict,
                    "adjusted_severity": v["adjusted_severity"],
                })
        else:
            unprocessed += 1

    # Compute Phase 04 impact metrics
    p04_tp = sum(v for (verdict, label), v in confusion.items()
                 if verdict in ACCEPT_VERDICTS and label in TP_LABELS)
    p04_fn = sum(v for (verdict, label), v in confusion.items()
                 if verdict in REJECT_VERDICTS and label in TP_LABELS)
    p04_tn = sum(v for (verdict, label), v in confusion.items()
                 if verdict in REJECT_VERDICTS and label in FP_LABELS)
    p04_fp = sum(v for (verdict, label), v in confusion.items()
                 if verdict in ACCEPT_VERDICTS and label in FP_LABELS)

    # Baseline (Phase 03 only, no Phase 04 filtering)
    label_dist = Counter(row.get("auto_label", "") for row in labels)
    baseline_tp = sum(label_dist.get(l, 0) for l in TP_LABELS)
    baseline_fp = label_dist.get("fp_invalid", 0)
    baseline_unknown = label_dist.get("unknown", 0)

    return {
        "coverage": {
            "total_findings": total_findings,
            "phase04_processed": processed,
            "phase04_unprocessed": unprocessed,
            "coverage_pct": round(processed / total_findings * 100, 1) if total_findings else 0,
        },
        "baseline_phase03": {
            "confirmed_real": baseline_tp,
            "confirmed_fp": baseline_fp,
            "unknown": baseline_unknown,
            "label_distribution": dict(label_dist.most_common()),
        },
        "phase04_confusion": {
            "true_positive": p04_tp,
            "false_negative": p04_fn,
            "true_negative": p04_tn,
            "false_positive_retained": p04_fp,
        },
        "phase04_accuracy": {
            "correct": p04_tp + p04_tn,
            "incorrect": p04_fn + p04_fp,
            "total_evaluated": p04_tp + p04_fn + p04_tn + p04_fp,
        },
        "false_negatives": false_negatives,
        "false_positives_retained": false_positive_retained,
        "confusion_matrix_raw": {
            f"{verdict}|{label}": count
            for (verdict, label), count in sorted(confusion.items())
        },
    }


def print_report(result: dict) -> None:
    """Print human-readable analysis report."""
    cov = result["coverage"]
    print("=" * 70)
    print("Phase 04 FP/FN Analysis Report")
    print("=" * 70)

    print(f"\n--- Coverage ---")
    print(f"Total findings:      {cov['total_findings']}")
    print(f"Phase 04 processed:  {cov['phase04_processed']} ({cov['coverage_pct']}%)")
    print(f"Phase 04 pending:    {cov['phase04_unprocessed']}")

    bl = result["baseline_phase03"]
    print(f"\n--- Phase 03 Baseline ---")
    print(f"Confirmed real:  {bl['confirmed_real']}")
    print(f"Confirmed FP:    {bl['confirmed_fp']}")
    print(f"Unknown:         {bl['unknown']}")
    for label, count in bl["label_distribution"].items():
        print(f"  {label}: {count}")

    cm = result["phase04_confusion"]
    acc = result["phase04_accuracy"]
    print(f"\n--- Phase 04 Confusion Matrix (processed items only) ---")
    print(f"True Positive (accepted real):     {cm['true_positive']}")
    print(f"False Negative (rejected real):    {cm['false_negative']}")
    print(f"True Negative (rejected FP):       {cm['true_negative']}")
    print(f"FP Retained (accepted invalid):    {cm['false_positive_retained']}")
    if acc["total_evaluated"]:
        accuracy = acc["correct"] / acc["total_evaluated"] * 100
        print(f"Accuracy: {acc['correct']}/{acc['total_evaluated']} = {accuracy:.1f}%")

    if result["false_negatives"]:
        print(f"\n--- FALSE NEGATIVES (real findings incorrectly disputed) ---")
        for fn in result["false_negatives"]:
            print(f"  {fn['finding_id']} ({fn['repo']})")
            print(f"    Benchmark: {fn['benchmark_label']} | Sherlock #{fn['csv_issue_id']} ({fn['csv_severity']})")
            print(f"    Phase 04:  {fn['phase04_verdict']} → {fn['adjusted_severity']}")
            print(f"    Title:     {fn['csv_title'][:80]}")
            print(f"    Notes:     {fn['reviewer_notes'][:120]}...")
            print()

    if result["false_positives_retained"]:
        print(f"\n--- FP RETAINED (invalid findings incorrectly accepted) ---")
        for fp in result["false_positives_retained"]:
            print(f"  {fp['finding_id']} ({fp['repo']})")
            print(f"    Benchmark: {fp['benchmark_label']} | Sherlock #{fp['csv_issue_id']}")
            print(f"    Phase 04:  {fp['phase04_verdict']} → {fp['adjusted_severity']}")
            print()

    if result["confusion_matrix_raw"]:
        print(f"\n--- Raw Confusion Matrix ---")
        for key, count in result["confusion_matrix_raw"].items():
            verdict, label = key.split("|")
            print(f"  {verdict:30s} × {label:15s} = {count}")

    print("\n" + "=" * 70)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Phase 04 FP/FN analysis")
    parser.add_argument(
        "--labels-csv",
        default="benchmarks/results/rq1/sherlock_ethereum_audit_contest/findings_labels.csv",
        help="Path to findings_labels.csv",
    )
    parser.add_argument(
        "--partials-pattern",
        default="outputs/04_PARTIAL_*.json",
        help="Glob pattern for Phase 04 PARTIAL files",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional path to write JSON results",
    )
    args = parser.parse_args()

    verdicts = load_phase04_verdicts(args.partials_pattern)
    print(f"[phase04] Loaded {len(verdicts)} Phase 04 verdicts")

    labels = load_benchmark_labels(args.labels_csv)
    print(f"[phase04] Loaded {len(labels)} benchmark labels")

    result = analyze(verdicts, labels)
    print_report(result)

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n[phase04] JSON output: {out_path}")


if __name__ == "__main__":
    main()
