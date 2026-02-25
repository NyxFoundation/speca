#!/usr/bin/env python3
"""Accurate FP/FN analysis of Phase 04 results vs ground truth."""
import json, glob, csv, textwrap

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

# Classification - include "tp" and "tp_info" as real
positive_verdicts = {"CONFIRMED_VULNERABILITY"}
real_labels = {"tp_valid", "tp", "tp_info", "partially_fixed", "fixed"}
fp_labels = {"fp_invalid", "fp_low", "fp_dup"}

tp_list = []
fp_list = []
fn_list = []
tn_list = []
ambiguous = []

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
        "reviewer_notes": item.get("reviewer_notes", ""),
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
print("PHASE 04 ACCURACY ANALYSIS (corrected)")
print(f"Total reviewed: {len(p04)}")
print(f"  TRUE POSITIVES:  {len(tp_list)}  (Phase04=CONFIRMED_VULN, GT=real)")
print(f"  FALSE POSITIVES: {len(fp_list)}  (Phase04=CONFIRMED_VULN, GT=fp)")
print(f"  TRUE NEGATIVES:  {len(tn_list)}  (Phase04=rejected/downgraded, GT=fp)")
print(f"  FALSE NEGATIVES: {len(fn_list)}  (Phase04=rejected/downgraded, GT=real)")
print(f"  AMBIGUOUS:       {len(ambiguous)}  (GT unknown/missing)")
if tp_list or fp_list:
    precision = len(tp_list) / (len(tp_list) + len(fp_list))
    print(f"  PRECISION:       {precision:.1%}")
if tp_list or fn_list:
    recall = len(tp_list) / (len(tp_list) + len(fn_list))
    print(f"  RECALL:          {recall:.1%}")
print("=" * 80)

def print_group(title, items):
    print(f"\n{'='*80}")
    print(f"  {title} ({len(items)})")
    print(f"{'='*80}")
    for e in items:
        print(f"\n  --- {e['pid']} ---")
        print(f"    Phase 04 verdict: {e['verdict']}  |  GT: {e['auto_label']}  |  Adj sev: {e['adjusted_severity']}")
        print(f"    Repo: {e['repo']}  |  CSV sev: {e['csv_severity']}")
        if e['csv_title']:
            print(f"    Contest title: {e['csv_title']}")
        print(f"    Reviewer notes:")
        for line in textwrap.wrap(e['reviewer_notes'], 95):
            print(f"      {line}")

print_group("FALSE POSITIVES (Phase 04 confirmed but GT=fp) - NEED TO REDUCE", fp_list)
print_group("FALSE NEGATIVES (Phase 04 rejected but GT=real) - NEED TO PRESERVE", fn_list)
print_group("TRUE POSITIVES", tp_list)
print_group("TRUE NEGATIVES", tn_list)
print_group("AMBIGUOUS", ambiguous)

# Pattern analysis for FPs
print("\n" + "=" * 80)
print("  FP PATTERN ANALYSIS")
print("=" * 80)
fp_patterns = {}
for e in fp_list:
    notes = e['reviewer_notes'].lower()
    patterns = []
    if 'sync path' in notes or 'sync' in notes:
        patterns.append('sync_vs_gossip_path_distinction')
    if 'spec' in notes and ('deviation' in notes or 'requires' in notes or 'cross-reference' in notes):
        patterns.append('spec_deviation_overclaim')
    if 'defense-in-depth' in notes or 'downstream' in notes:
        patterns.append('defense_in_depth_reasoning')
    if 'verified' in notes and 'code reading' in notes:
        patterns.append('code_reading_verified')
    if not patterns:
        patterns.append('other')
    for p in patterns:
        fp_patterns.setdefault(p, []).append(e['pid'])

for pattern, pids in sorted(fp_patterns.items(), key=lambda x: -len(x[1])):
    print(f"\n  Pattern: {pattern} ({len(pids)} FPs)")
    for pid in pids:
        print(f"    - {pid}")

# Check contest issue grouping
print("\n" + "=" * 80)
print("  FP CONTEST ISSUE GROUPING")
print("=" * 80)
issue_groups = {}
for e in fp_list:
    title = e['csv_title'] or "no_title"
    issue_groups.setdefault(title, []).append(e['pid'])
for title, pids in issue_groups.items():
    print(f"\n  Contest issue: '{title}'")
    print(f"  Properties: {len(pids)}")
    for pid in pids:
        print(f"    - {pid}")
