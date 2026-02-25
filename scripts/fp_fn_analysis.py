#!/usr/bin/env python3
"""Accurate FP/FN analysis of Phase 04 results vs ground truth."""
import json, glob, csv

# Parse Phase 04 partials
partials = sorted(glob.glob("outputs/04_PARTIAL_*.json"))
p04 = {}
for p in partials:
    with open(p) as f:
        data = json.load(f)
    for item in data.get("reviewed_items", []):
        pid = item.get("property_id", "")
        if pid:
            p04[pid] = item

# Parse ground truth
gt = {}
with open("benchmarks/results/rq1/sherlock_ethereum_audit_contest/findings_labels.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        gt[row["finding_id"].strip()] = row

# Classification
positive_verdicts = {"CONFIRMED_VULNERABILITY"}
real_labels = {"tp_valid", "partially_fixed", "fixed"}
fp_labels = {"fp_invalid", "fp_low", "fp_dup"}

tp_list = []  # Phase04=positive, GT=real
fp_list = []  # Phase04=positive, GT=fp
fn_list = []  # Phase04=negative, GT=real
tn_list = []  # Phase04=negative, GT=fp
ambiguous = []  # GT unknown

for pid, item in sorted(p04.items()):
    verdict = item.get("review_verdict", "")
    g = gt.get(pid, {})
    auto_label = g.get("auto_label", "").strip()
    repo = g.get("repo", "")
    csv_sev = g.get("csv_severity", "")
    csv_title = g.get("csv_title", "")

    phase04_positive = verdict in positive_verdicts
    gt_real = auto_label in real_labels
    gt_fp = auto_label in fp_labels

    entry = {
        "pid": pid,
        "verdict": verdict,
        "auto_label": auto_label,
        "repo": repo,
        "csv_severity": csv_sev,
        "csv_title": csv_title,
        "adjusted_severity": item.get("adjusted_severity", ""),
        "original_classification": item.get("original_classification", ""),
        "reviewer_notes": item.get("reviewer_notes", "")[:200],
    }

    if auto_label == "" or auto_label == "unknown":
        ambiguous.append(entry)
    elif phase04_positive and gt_real:
        tp_list.append(entry)
    elif phase04_positive and gt_fp:
        fp_list.append(entry)
    elif not phase04_positive and gt_real:
        fn_list.append(entry)
    elif not phase04_positive and gt_fp:
        tn_list.append(entry)
    else:
        ambiguous.append(entry)

print("=" * 80)
print(f"PHASE 04 ACCURACY ANALYSIS")
print(f"Total reviewed: {len(p04)}")
print(f"  TRUE POSITIVES:  {len(tp_list)}  (Phase04=CONFIRMED, GT=real)")
print(f"  FALSE POSITIVES: {len(fp_list)}  (Phase04=CONFIRMED, GT=fp)")
print(f"  TRUE NEGATIVES:  {len(tn_list)}  (Phase04=rejected, GT=fp)")
print(f"  FALSE NEGATIVES: {len(fn_list)}  (Phase04=rejected, GT=real)")
print(f"  AMBIGUOUS:       {len(ambiguous)}  (GT unknown/missing)")
print("=" * 80)

def print_group(title, items):
    print(f"\n### {title} ({len(items)})")
    for e in items:
        print(f"\n  {e['pid']}")
        print(f"    Verdict:      {e['verdict']}")
        print(f"    GT label:     {e['auto_label']}")
        print(f"    Repo:         {e['repo']}")
        print(f"    CSV severity: {e['csv_severity']}")
        print(f"    CSV title:    {e['csv_title']}")
        print(f"    Adj severity: {e['adjusted_severity']}")
        print(f"    Notes:        {e['reviewer_notes']}...")

print_group("FALSE POSITIVES (Phase 04 confirmed but GT=fp)", fp_list)
print_group("FALSE NEGATIVES (Phase 04 rejected but GT=real)", fn_list)
print_group("TRUE POSITIVES", tp_list)
print_group("TRUE NEGATIVES", tn_list)
print_group("AMBIGUOUS (GT unknown)", ambiguous)
