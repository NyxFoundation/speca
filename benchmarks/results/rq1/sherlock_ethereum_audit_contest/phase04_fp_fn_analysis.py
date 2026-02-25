#!/usr/bin/env python3
"""
Phase 04 False Positive / False Negative Analysis

Cross-references Phase 04 review verdicts against ground truth labels
from the Sherlock Ethereum audit contest benchmark.

NOTE: The CSV has duplicate finding_ids across repos (same property checked
against multiple clients). Phase 04 items all target status-im/nimbus-eth2,
so we key ground truth by (finding_id, repo) to get the correct label.
"""

import csv
import json
import glob
import os
from collections import defaultdict, Counter
from pathlib import Path

BASE_DIR = Path(__file__).parent
OUTPUTS_DIR = BASE_DIR.parent.parent.parent.parent / "outputs"

# All Phase 04 items in this run target Nimbus
PHASE04_TARGET_REPO = "status-im/nimbus-eth2"


# ── 1. Load ground truth labels ──────────────────────────────────────────────
def load_ground_truth(csv_path: str) -> tuple[dict, list[dict]]:
    """Load findings_labels.csv into {(finding_id, repo): row_dict} and flat list."""
    gt_by_key = {}
    gt_rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fid = row["finding_id"].strip()
            repo = row["repo"].strip()
            entry = {
                "finding_id": fid,
                "repo": repo,
                "classification": row["classification"].strip(),
                "auto_label": row["auto_label"].strip(),
                "csv_issue_id": row.get("csv_issue_id", "").strip(),
                "csv_severity": row.get("csv_severity", "").strip(),
                "csv_title": row.get("csv_title", "").strip(),
                "human_label": row.get("human_label", "").strip(),
            }
            gt_by_key[(fid, repo)] = entry
            gt_rows.append(entry)
    return gt_by_key, gt_rows


# ── 2. Load Phase 04 partial results ────────────────────────────────────────
def load_phase04_verdicts(outputs_dir: str) -> list[dict]:
    """Load all 04_PARTIAL_*.json files and extract review verdicts."""
    verdicts = []
    partial_files = sorted(glob.glob(os.path.join(outputs_dir, "04_PARTIAL_*.json")))
    for pf in partial_files:
        with open(pf) as f:
            data = json.load(f)
        for item in data.get("reviewed_items", []):
            verdicts.append({
                "property_id": item["property_id"],
                "review_verdict": item["review_verdict"],
                "original_classification": item.get("original_classification", ""),
                "adjusted_severity": item.get("adjusted_severity", ""),
                "reviewer_notes": item.get("reviewer_notes", ""),
                "source_file": os.path.basename(pf),
            })
    return verdicts


# ── 3. Classification helpers ────────────────────────────────────────────────

# Ground truth: which auto_labels count as "real vulnerability"
GROUND_TRUTH_POSITIVE = {"tp", "tp_info", "fixed", "partially_fixed"}
GROUND_TRUTH_NEGATIVE = {"fp_invalid"}

# Phase 04 verdict: which verdicts count as "positive" (confirmed real)
PHASE04_POSITIVE = {"CONFIRMED_VULNERABILITY", "LIKELY_VULNERABILITY"}
PHASE04_NEGATIVE = {"DISPUTED_FP", "FALSE_POSITIVE", "DESIGN_CHOICE", "REQUIRES_MANUAL_REVIEW"}


def classify_gt(auto_label: str) -> str:
    if auto_label in GROUND_TRUTH_POSITIVE:
        return "positive"
    elif auto_label in GROUND_TRUTH_NEGATIVE:
        return "negative"
    return "unknown"


def classify_p04(verdict: str) -> str:
    if verdict in PHASE04_POSITIVE:
        return "positive"
    return "negative"


# ── 4. Main analysis ────────────────────────────────────────────────────────
def main():
    gt_by_key, gt_rows = load_ground_truth(str(BASE_DIR / "findings_labels.csv"))
    verdicts = load_phase04_verdicts(str(OUTPUTS_DIR))

    print("=" * 80)
    print("PHASE 04 FALSE POSITIVE / FALSE NEGATIVE ANALYSIS")
    print("=" * 80)

    # ── Overview ──
    print(f"\n## Overview")
    print(f"  Total rows in ground truth CSV        : {len(gt_rows)}")
    print(f"  Unique (finding_id, repo) pairs        : {len(gt_by_key)}")
    print(f"  Phase 04 reviewed items                : {len(verdicts)}")
    print(f"  Phase 04 target repo                   : {PHASE04_TARGET_REPO}")
    gt_label_dist = Counter(r["auto_label"] for r in gt_rows)
    print(f"  Ground truth label distribution (rows) : {dict(gt_label_dist)}")

    # Nimbus-specific counts
    nimbus_rows = [r for r in gt_rows if r["repo"] == PHASE04_TARGET_REPO]
    nimbus_label_dist = Counter(r["auto_label"] for r in nimbus_rows)
    print(f"  Nimbus rows in CSV                     : {len(nimbus_rows)}")
    print(f"  Nimbus label distribution              : {dict(nimbus_label_dist)}")

    # ── Phase 04 verdict distribution ──
    verdict_dist = Counter(v["review_verdict"] for v in verdicts)
    print(f"\n## Phase 04 Verdict Distribution")
    for v, c in sorted(verdict_dist.items()):
        print(f"  {v:30s} : {c}")

    # ── Detailed per-item comparison ──
    print(f"\n## Per-Item Comparison (Phase 04 vs Nimbus Ground Truth)")
    print(f"  {'Property ID':42s} {'P04 Verdict':28s} {'GT Label':18s} {'Sev':8s} {'Result':6s}")
    print("  " + "-" * 106)

    tp = fp = tn = fn = unknown_count = 0
    fp_details = []
    fn_details = []

    for v in verdicts:
        pid = v["property_id"]
        p04_verdict = v["review_verdict"]
        p04_class = classify_p04(p04_verdict)

        # Look up ground truth for this finding + Nimbus repo
        key = (pid, PHASE04_TARGET_REPO)
        if key in gt_by_key:
            gt_entry = gt_by_key[key]
            gt_label = gt_entry["auto_label"]
            gt_severity = gt_entry["csv_severity"]
            gt_title = gt_entry["csv_title"]
            gt_class = classify_gt(gt_label)

            if gt_class == "unknown":
                result = "N/A"
                unknown_count += 1
            elif p04_class == "positive" and gt_class == "positive":
                result = "TP"
                tp += 1
            elif p04_class == "positive" and gt_class == "negative":
                result = "FP"
                fp += 1
                fp_details.append({
                    "property_id": pid, "verdict": p04_verdict,
                    "gt_label": gt_label, "title": gt_title,
                    "notes": v["reviewer_notes"][:120],
                })
            elif p04_class == "negative" and gt_class == "negative":
                result = "TN"
                tn += 1
            elif p04_class == "negative" and gt_class == "positive":
                result = "FN"
                fn += 1
                fn_details.append({
                    "property_id": pid, "verdict": p04_verdict,
                    "gt_label": gt_label, "severity": gt_severity, "title": gt_title,
                    "notes": v["reviewer_notes"][:120],
                })
            else:
                result = "?"
        else:
            gt_label = "NOT_IN_CSV"
            gt_severity = ""
            result = "N/A"
            unknown_count += 1

        print(f"  {pid:40s}  {p04_verdict:28s} {gt_label:18s} {gt_severity:8s} {result:6s}")

    # ── Confusion Matrix ──
    labeled_total = tp + fp + tn + fn
    print(f"\n## Confusion Matrix (labeled items only, n={labeled_total})")
    print(f"                          Ground Truth")
    print(f"                      Positive   Negative")
    print(f"  P04 Positive      {tp:5d} (TP)  {fp:5d} (FP)")
    print(f"  P04 Negative      {fn:5d} (FN)  {tn:5d} (TN)")
    print(f"  Unlabeled/unknown items excluded: {unknown_count}")

    # ── Metrics ──
    print(f"\n## Metrics")
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    accuracy = (tp + tn) / labeled_total if labeled_total > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0

    print(f"  Precision  (P04 confirmed → real)    : {precision:.1%} ({tp}/{tp+fp})")
    print(f"  Recall     (real vulns → confirmed)   : {recall:.1%} ({tp}/{tp+fn})")
    print(f"  Specificity (FP rejected correctly)   : {specificity:.1%} ({tn}/{tn+fp})")
    print(f"  Accuracy                              : {accuracy:.1%} ({tp+tn}/{labeled_total})")
    print(f"  F1 Score                              : {f1:.3f}")

    # ── FP Details ──
    if fp_details:
        print(f"\n## False Positives — Phase 04 CONFIRMED but ground truth fp_invalid ({len(fp_details)})")
        for d in fp_details:
            print(f"  * {d['property_id']}")
            print(f"    P04: {d['verdict']}  |  GT: {d['gt_label']}")
            if d["title"]:
                print(f"    Contest issue: {d['title']}")
            print(f"    P04 reasoning (excerpt): {d['notes']}...")

    # ── FN Details ──
    if fn_details:
        print(f"\n## False Negatives — Phase 04 DISPUTED but ground truth positive ({len(fn_details)})")
        for d in fn_details:
            print(f"  * {d['property_id']}")
            print(f"    P04: {d['verdict']}  |  GT: {d['gt_label']} (severity={d['severity']})")
            if d["title"]:
                print(f"    Contest issue: {d['title']}")
            print(f"    P04 reasoning (excerpt): {d['notes']}...")

    # ── Coverage analysis across all repos ──
    reviewed_ids = {v["property_id"] for v in verdicts}
    all_nimbus_ids = {r["finding_id"] for r in nimbus_rows}
    nimbus_not_reviewed = all_nimbus_ids - reviewed_ids
    nimbus_reviewed = all_nimbus_ids & reviewed_ids

    print(f"\n## Coverage Analysis")
    print(f"  Nimbus findings in CSV             : {len(all_nimbus_ids)}")
    print(f"  Nimbus findings reviewed by P04    : {len(nimbus_reviewed)}")
    print(f"  Nimbus findings NOT reviewed by P04: {len(nimbus_not_reviewed)}")
    if nimbus_not_reviewed:
        print(f"  Unreviewed Nimbus finding IDs: {nimbus_not_reviewed}")

    # Cross-repo coverage
    all_repos = sorted(set(r["repo"] for r in gt_rows))
    print(f"\n  All-repo coverage:")
    print(f"  {'Repo':40s} {'Total':>6s} {'P04':>5s} {'TP in GT':>9s} {'TP Missed':>10s}")
    for repo in all_repos:
        repo_rows = [r for r in gt_rows if r["repo"] == repo]
        repo_ids = {r["finding_id"] for r in repo_rows}
        repo_reviewed = repo_ids & reviewed_ids
        repo_tp = [r for r in repo_rows if classify_gt(r["auto_label"]) == "positive"]
        repo_tp_missed = [r for r in repo_tp if r["finding_id"] not in reviewed_ids]
        print(f"  {repo:40s} {len(repo_rows):>6d} {len(repo_reviewed):>5d} {len(repo_tp):>9d} {len(repo_tp_missed):>10d}")

    # ── Phase 03 overall precision context ──
    print(f"\n## Phase 03 Overall Precision (for context)")
    total_rows = len(gt_rows)
    total_pos = sum(1 for r in gt_rows if classify_gt(r["auto_label"]) == "positive")
    total_neg = sum(1 for r in gt_rows if classify_gt(r["auto_label"]) == "negative")
    total_unk = total_rows - total_pos - total_neg
    p03_precision_optimistic = total_pos / (total_pos + total_neg) if (total_pos + total_neg) > 0 else 0
    p03_precision_conservative = total_pos / total_rows if total_rows > 0 else 0
    print(f"  Total Phase 03 findings             : {total_rows}")
    print(f"  Ground truth POSITIVE               : {total_pos}")
    print(f"  Ground truth NEGATIVE (fp_invalid)   : {total_neg}")
    print(f"  Ground truth UNKNOWN                 : {total_unk}")
    print(f"  Phase 03 precision (labeled only)    : {p03_precision_optimistic:.1%}")
    print(f"  Phase 03 precision (conservative)    : {p03_precision_conservative:.1%}")

    # ── Output JSON summary ──
    summary = {
        "phase04_target_repo": PHASE04_TARGET_REPO,
        "phase04_items_reviewed": len(verdicts),
        "ground_truth_total_rows": len(gt_rows),
        "ground_truth_nimbus_rows": len(nimbus_rows),
        "confusion_matrix": {
            "TP": tp, "FP": fp, "TN": tn, "FN": fn, "unknown": unknown_count
        },
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "specificity": round(specificity, 4),
            "accuracy": round(accuracy, 4),
            "f1": round(f1, 4),
        },
        "false_positives": [
            {"property_id": d["property_id"], "verdict": d["verdict"],
             "gt_label": d["gt_label"], "title": d["title"]}
            for d in fp_details
        ],
        "false_negatives": [
            {"property_id": d["property_id"], "verdict": d["verdict"],
             "gt_label": d["gt_label"], "severity": d["severity"], "title": d["title"]}
            for d in fn_details
        ],
        "phase03_context": {
            "total_findings": total_rows,
            "precision_labeled": round(p03_precision_optimistic, 4),
            "precision_conservative": round(p03_precision_conservative, 4),
        },
    }
    summary_path = BASE_DIR / "phase04_fp_fn_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Summary JSON written to: {summary_path}")


if __name__ == "__main__":
    main()
