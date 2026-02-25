#!/usr/bin/env python3
"""Show Nimbus findings rejected/downgraded by Phase 04."""
import json, glob, csv, textwrap

# Parse Phase 04 partials
partials = glob.glob("outputs/04_PARTIAL_*.json")
p04 = {}
for p in sorted(partials):
    with open(p) as f:
        data = json.load(f)
    for item in data.get("reviewed_items", []):
        pid = item.get("property_id", "")
        if pid:
            p04[pid] = item

# Parse ground truth
gt = {}
with open(
    "benchmarks/results/rq1/sherlock_ethereum_audit_contest/findings_labels.csv"
) as f:
    reader = csv.DictReader(f)
    for row in reader:
        gt[row["finding_id"].strip()] = row

# Find Nimbus findings NOT marked CONFIRMED_VULNERABILITY
nimbus_rejected = []
for pid, item in p04.items():
    g = gt.get(pid, {})
    repo = g.get("repo", "")
    if "nimbus" not in repo.lower():
        continue
    verdict = item.get("review_verdict", "")
    if verdict != "CONFIRMED_VULNERABILITY":
        nimbus_rejected.append((pid, item, g))

print(f"Nimbus findings rejected/downgraded by Phase 04: {len(nimbus_rejected)}")
print()
for pid, item, g in sorted(nimbus_rejected, key=lambda x: x[0]):
    print(f"=== {pid} ===")
    print(f"  Phase 03 classification: {item.get('original_classification', '')}")
    print(f"  Phase 04 verdict:        {item.get('review_verdict', '')}")
    print(f"  Adjusted severity:       {item.get('adjusted_severity', '')}")
    print(f"  GT auto_label:           {g.get('auto_label', '')}")
    print(f"  GT csv_severity:         {g.get('csv_severity', '')}")
    print(f"  GT csv_title:            {g.get('csv_title', '')}")
    hl = g.get("human_label", "")
    if hl:
        print(f"  GT human_label:          {hl}")
    print()
    notes = item.get("reviewer_notes", "")
    print("  Reviewer notes:")
    for line in textwrap.wrap(notes, 100):
        print(f"    {line}")
    print()
    spec = item.get("spec_reference", "")
    if spec:
        print("  Spec reference:")
        for line in textwrap.wrap(spec, 100):
            print(f"    {line}")
    print()
    print("---")
    print()
