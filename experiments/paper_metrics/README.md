# Paper-revision recompute scripts (#107 / #110 — and the #103/#104 gap)

Recomputes the denominators and per-type numbers the reviewers asked to be made
rigorous, straight from Phase 03/04 outputs. Numbers are one command away once
the run outputs (findings data) are available; the scripts are self-tested so
the *logic* is verified now, without that data.

## What computes from existing outputs (verified)

- **`property_type_precision.py` (#110)** — joins Phase 01e `Property.type`
  (invariant / precondition / postcondition / assumption) to Phase 04
  `review_verdict` (Confirmed = TP, Disputed = FP) by `property_id`; reports
  per-type TP/FP/precision and overall precision **with and without** the
  `assumption` type. This is exactly the #110 "gate + report both numbers"
  evidence (paper Table IX). `--selftest` reproduces the invariant-75% /
  assumption-0% / before-after-gate structure.
- **`build_population_table.py` (#107)** — the single denominator chain
  `raw -> positive -> adjudicated -> clusters -> GT-match`. The first three
  counts come from `AuditMapItem.classification` and `ReviewedItem.review_verdict`
  directly. `--selftest` verifies the counting.

Both are grounded in `scripts/orchestrator/schemas.py` (AuditMapItem,
ReviewedItem, Property) and use only fields that exist there.

## What does NOT compute from existing outputs — the #103/#104 provenance gap

Writing these scripts surfaced a structural gap that matters for the rebuttal:

1. **No auto-vs-expert provenance on properties (#103, A(2)).** `Property` has
   `type` but **no field recording whether a property was auto-generated (01e)
   or expert-authored**. So the paper's "expert-augmented 15/15 vs
   automated-only 8/15" split, and specifically the **KZG detecting property's
   origin**, cannot be recovered from `outputs/` alone — it lives only in the
   run design (which run was the expert-augmented pass) or must be labeled by
   hand. This is why #103's KZG-origin item is "confirm from the run
   configuration", not "read a field".
   - **Recommendation:** add `provenance: "auto" | "expert"` to `Property`
     (and thread it through 01e / the expert-augmentation path) so future runs
     record it structurally. Until then, label the ~15 detecting properties
     manually and mark the estimate as retrospective (per #103).

2. **No structured FP root-cause on reviewed items (#104, B(4)).**
   `ReviewedItem` has free-text `reviewer_notes` but **no enum root cause**
   (trust-boundary / code-reading / spec-misinterpretation). The paper's IV-C4
   3-way split of the 16 FPs was a manual analysis, so per-phase hallucination
   rates can't be auto-tallied yet.
   - **Recommendation:** add `fp_root_cause` (enum) to `ReviewedItem` so #104's
     per-phase accounting is computed, not hand-labeled.

`build_population_table.py` prints these gaps in its `_note` and leaves the
`clusters` / `gt_match` cells as "REQUIRES external map" rather than inventing
numbers.

## Clusters and ground-truth matching

Neither is a pipeline output. Pass them as external maps when available:
`--clusters property_id->cluster_id.json`, `--gt property_id->gt_id.json`.

## Run

```
python property_type_precision.py --selftest
python property_type_precision.py --e01e 'outputs/01e_PARTIAL_*.json' --p04 'outputs/04_PARTIAL_*.json'

python build_population_table.py --selftest
python build_population_table.py --p03 'outputs/03_PARTIAL_*.json' --p04 'outputs/04_PARTIAL_*.json' \
    [--clusters clusters.json] [--gt gt_map.json]
```
