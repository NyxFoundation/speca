#!/usr/bin/env python3
"""Analyze Phase 04 results against ground truth labels."""

import json
import glob
import csv
from collections import defaultdict, Counter

# 1. Parse all Phase 04 PARTIAL files
partials = glob.glob("outputs/04_PARTIAL_*.json")
phase04_findings = {}
for p in sorted(partials):
    with open(p) as f:
        data = json.load(f)
    for item in data.get("reviewed_items", []):
        pid = item.get("property_id", "")
        if pid:
            phase04_findings[pid] = {
                "verdict": item.get("review_verdict", ""),
                "original_classification": item.get("original_classification", ""),
                "adjusted_severity": item.get("adjusted_severity", ""),
                "reviewer_notes": item.get("reviewer_notes", "")[:120],
            }

print(f"Total Phase 04 reviewed findings: {len(phase04_findings)}")
print()

# Verdict distribution
verdict_counts = Counter(v["verdict"] for v in phase04_findings.values())
print("=== Phase 04 Verdict Distribution ===")
for vd, cnt in verdict_counts.most_common():
    print(f"  {vd}: {cnt}")
print()

# 2. Parse ground truth CSV
gt = {}
with open(
    "benchmarks/results/rq1/sherlock_ethereum_audit_contest/findings_labels.csv"
) as f:
    reader = csv.DictReader(f)
    for row in reader:
        fid = row["finding_id"].strip()
        gt[fid] = {
            "auto_label": row.get("auto_label", "").strip(),
            "csv_issue_id": row.get("csv_issue_id", "").strip(),
            "csv_severity": row.get("csv_severity", "").strip(),
            "csv_title": row.get("csv_title", "").strip(),
            "human_label": row.get("human_label", "").strip(),
            "classification": row.get("classification", "").strip(),
            "repo": row.get("repo", "").strip(),
        }

print(f"Total ground truth entries: {len(gt)}")
gt_label_counts = Counter(v["auto_label"] for v in gt.values())
print("=== Ground Truth Label Distribution ===")
for lab, cnt in gt_label_counts.most_common():
    print(f"  {repr(lab)}: {cnt}")
print()

# 3. Cross-reference
positive_verdicts = {"CONFIRMED_VULNERABILITY", "LIKELY_VULNERABILITY"}
negative_verdicts = {
    "FALSE_POSITIVE",
    "NOT_A_VULNERABILITY",
    "INSUFFICIENT_EVIDENCE",
    "REQUIRES_MANUAL_REVIEW",
}

real_labels = {"tp", "tp_info"}
fp_labels = {"fp_invalid"}
fixed_labels = {"fixed", "partially_fixed"}

matched = 0
unmatched_in_gt = 0

confusion = defaultdict(list)

for fid, p04 in phase04_findings.items():
    if fid in gt:
        matched += 1
        label = gt[fid]["auto_label"]
        verdict = p04["verdict"]

        is_positive = verdict in positive_verdicts
        is_negative = verdict in negative_verdicts

        if label in real_labels:
            if is_positive:
                confusion["TP"].append(fid)
            elif is_negative:
                confusion["FN"].append(fid)
            else:
                confusion["AMBIG_REAL"].append(fid)
        elif label in fp_labels:
            if is_positive:
                confusion["FP"].append(fid)
            elif is_negative:
                confusion["TN"].append(fid)
            else:
                confusion["AMBIG_FP"].append(fid)
        elif label in fixed_labels:
            if is_positive:
                confusion["TP_FIXED_POS"].append(fid)
            elif is_negative:
                confusion["FIXED_NEG"].append(fid)
            else:
                confusion["FIXED_AMBIG"].append(fid)
        elif label == "unknown" or label == "":
            confusion["UNKNOWN_LABEL"].append(fid)
    else:
        unmatched_in_gt += 1

print(f"Matched with ground truth: {matched}")
print(f"Not in ground truth (no label): {unmatched_in_gt}")
print()

print("=== Confusion Matrix (labeled findings only) ===")
tp_count = len(confusion["TP"])
fp_count = len(confusion["FP"])
fn_count = len(confusion["FN"])
tn_count = len(confusion["TN"])
print(f"  True Positives  (TP): {tp_count}")
print(f"  False Positives (FP): {fp_count}")
print(f"  False Negatives (FN): {fn_count}")
print(f"  True Negatives  (TN): {tn_count}")
print()

precision = recall = f1 = 0.0
if tp_count + fp_count > 0:
    precision = tp_count / (tp_count + fp_count)
    print(f"  Precision: {precision:.2%} ({tp_count}/{tp_count + fp_count})")
if tp_count + fn_count > 0:
    recall = tp_count / (tp_count + fn_count)
    print(f"  Recall:    {recall:.2%} ({tp_count}/{tp_count + fn_count})")
if precision + recall > 0:
    f1 = 2 * precision * recall / (precision + recall)
    print(f"  F1 Score:  {f1:.2%}")
print()

# Including tp_info as separate category
tp_strict = sum(
    1
    for fid in confusion["TP"]
    if gt[fid]["auto_label"] == "tp"
)
tp_info = sum(
    1
    for fid in confusion["TP"]
    if gt[fid]["auto_label"] == "tp_info"
)
fn_strict = sum(
    1
    for fid in confusion["FN"]
    if gt[fid]["auto_label"] == "tp"
)
fn_info = sum(
    1
    for fid in confusion["FN"]
    if gt[fid]["auto_label"] == "tp_info"
)
print("=== TP/FN breakdown by severity ===")
print(f"  TP (high/medium/low - tp):    {tp_strict}")
print(f"  TP (informational - tp_info): {tp_info}")
print(f"  FN (high/medium/low - tp):    {fn_strict}")
print(f"  FN (informational - tp_info): {fn_info}")
print()

# Fixed/partially_fixed
print(f"  Fixed issues flagged as positive: {len(confusion['TP_FIXED_POS'])}")
print(f"  Fixed issues flagged as negative: {len(confusion['FIXED_NEG'])}")
print(f"  Unknown-label findings:           {len(confusion['UNKNOWN_LABEL'])}")
print()

# Detail: FP list
print("=== False Positives (pipeline positive, GT=fp_invalid) ===")
for fid in sorted(confusion["FP"]):
    v = phase04_findings[fid]
    g = gt[fid]
    hl = g["human_label"]
    print(f"  {fid}")
    print(f"    Verdict: {v['verdict']}, Sev: {v['adjusted_severity']}")
    print(f"    GT: {g['csv_severity']} - {g['csv_title'][:90]}")
    if hl:
        print(f"    Note: {hl}")
    print()

# Detail: FN list
print("=== False Negatives (pipeline negative, GT=tp/tp_info) ===")
for fid in sorted(confusion["FN"]):
    v = phase04_findings[fid]
    g = gt[fid]
    print(f"  {fid}")
    print(f"    Verdict: {v['verdict']}, Sev: {v['adjusted_severity']}")
    print(f"    GT: {g['auto_label']}, {g['csv_severity']} - {g['csv_title'][:90]}")
    print()

# Detailed per-verdict x per-label breakdown
print("=== Detailed Verdict x Label Cross-tab ===")
cross = defaultdict(lambda: defaultdict(int))
for fid, p04 in phase04_findings.items():
    if fid in gt:
        label = gt[fid]["auto_label"] or "no_label"
        cross[p04["verdict"]][label] += 1

for verdict in sorted(cross.keys()):
    labels = cross[verdict]
    parts = ", ".join(
        f"{l}={c}" for l, c in sorted(labels.items(), key=lambda x: -x[1])
    )
    print(f"  {verdict}: {parts}")
print()

# Severity analysis for TPs
print("=== True Positive Severity Analysis ===")
sev_match = {"match": 0, "mismatch": 0, "na": 0}
for fid in sorted(confusion["TP"]):
    g = gt[fid]
    v = phase04_findings[fid]
    gt_sev = g["csv_severity"].lower()
    adj_sev = v["adjusted_severity"].lower()
    match_str = "MATCH" if gt_sev == adj_sev else "MISMATCH"
    if gt_sev == adj_sev:
        sev_match["match"] += 1
    else:
        sev_match["mismatch"] += 1
    title = g["csv_title"][:70]
    print(
        f"  {fid}: pipeline={v['adjusted_severity']}, GT={g['csv_severity']} [{match_str}] ({title})"
    )
print()
print(
    f"  Severity match rate: {sev_match['match']}/{sev_match['match'] + sev_match['mismatch']}"
)
print()

# Per-repo breakdown
print("=== Per-Repository Results ===")
repo_stats = defaultdict(lambda: {"TP": 0, "FP": 0, "FN": 0, "TN": 0, "other": 0})
for fid, p04 in phase04_findings.items():
    if fid in gt:
        label = gt[fid]["auto_label"]
        repo = gt[fid]["repo"]
        verdict = p04["verdict"]
        is_positive = verdict in positive_verdicts
        is_negative = verdict in negative_verdicts

        if label in real_labels:
            if is_positive:
                repo_stats[repo]["TP"] += 1
            elif is_negative:
                repo_stats[repo]["FN"] += 1
            else:
                repo_stats[repo]["other"] += 1
        elif label in fp_labels:
            if is_positive:
                repo_stats[repo]["FP"] += 1
            elif is_negative:
                repo_stats[repo]["TN"] += 1
            else:
                repo_stats[repo]["other"] += 1
        else:
            repo_stats[repo]["other"] += 1

for repo in sorted(repo_stats.keys()):
    s = repo_stats[repo]
    total = s["TP"] + s["FP"] + s["FN"] + s["TN"]
    p_str = "N/A"
    r_str = "N/A"
    if s["TP"] + s["FP"] > 0:
        p_str = f"{s['TP'] / (s['TP'] + s['FP']):.0%}"
    if s["TP"] + s["FN"] > 0:
        r_str = f"{s['TP'] / (s['TP'] + s['FN']):.0%}"
    print(
        f"  {repo}: TP={s['TP']} FP={s['FP']} FN={s['FN']} TN={s['TN']} other={s['other']} | P={p_str} R={r_str}"
    )
