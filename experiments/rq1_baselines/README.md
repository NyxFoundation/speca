# RQ1 Controlled Baselines (issue #102)

Decision experiment for reviewer comments **#1756A(1)** (missing controlled
baseline) and **#1756B(5)** (framework vs. base-model). Its result gates the
paper's framing decisions in #106 (generality) and #111 (deployment reframe),
so it runs **first**.

> Status: **design + scaffold**. Prompts and protocol are ready. The runner
> (`run_arms.py`) is a skeleton documenting the exact wiring; it needs the two
> variant audit phases registered in `scripts/orchestrator/config.py`, the arm
> A/B **queue builder** (below), and **one smoke-test run** before its numbers
> can be trusted. Nothing here has been executed (no compute budget / findings
> data in this environment).
>
> Revised per @grandchildrice's PR #125 review: output schema now matches the
> real Phase 03 contract; env wiring and the run terminology are corrected;
> queue-generation fairness is specified.

## Three arms — vary only the front-end, hold the audit/review constant

The pipeline is `01a -> 01b -> 01e -> 02c -> 03 -> 04`. Only the property
front-end is varied; the audit reasoning output contract and the Phase-04 review
gates are held constant, so any delta is attributable to the property
scaffolding, not to a different judge or a different output shape.

| Arm | Input given to the auditor | Phases run | Audit prompt |
|-----|----------------------------|------------|--------------|
| **A. code-only-LLM** | in-scope code units only (no spec, no properties) | 03_codeonly -> 04 | `prompts/audit_code_only.md` |
| **B. spec-only-no-properties** | spec text + subgraph, **no typed properties** | 01a -> 01b -> 03_spec_only -> 04 | `prompts/audit_spec_only.md` |
| **C. SPECA full** | typed properties + resolved code scope | 01a -> 01b -> 01e -> 02c -> 03 -> 04 | `prompts/03_auditmap_worker_inline.md` (unchanged) |

## Output contract (all arms identical — required for a fair 04)

The real Phase 03 emits a single JSON object `{metadata, audit_items}` where each
`audit_items` row has EXACTLY six keys: `property_id`, `classification`,
`code_path`, `proof_trace`, `attack_scenario`, `checklist_id` (no `severity`,
no `confidence`). Phase 04 consumes `outputs/03_PARTIAL_*.json` in that shape, so
the variant prompts emit the same contract:

- Arms A/B have no property, so `property_id` is a surrogate `armA-<NNN>` /
  `armB-<NNN>`, and `checklist_id = property_id`.
- Arm info goes in `metadata.arm`. Severity is recovered downstream from
  `BUG_BOUNTY_SCOPE` thresholds, exactly as for arm C.
- Arm B records its provenance (the informal spec obligation that surfaced the
  finding) as a `[obligation: ...]` prefix on `proof_trace`, so #103 can tell
  arm-B findings from arm-C typed-property findings.

## Queue generation and fairness (the causal-validity crux)

Phase 03's audit queue is normally derived from Phase 02c (properties resolved to
code). Arms A/B skip 02c, so their audit units must be built explicitly, and they
must cover the **same in-scope code population arm C sees** — otherwise arm A's
recall moves with the code surface, not with the presence/absence of properties,
and the A(1) causal claim is muddied. Rule:

- **Arm A queue**: the in-scope code units enumerated from
  `BUG_BOUNTY_SCOPE.json` in-scope components (functions/regions of the target),
  with **no property-derived filtering**. Same code population as C, zero
  property signal.
- **Arm B queue**: the Phase 01b subgraph regions mapped to code (spec-driven
  units), again with no typed-property filtering.

This queue builder is part of the wiring (step 2 in `run_arms.py`); it is not yet
implemented.

## Runs, not seeds (#102 directive 1, and per review point 5)

A "run" pins `SPECA_RUN_ID` for output determinism; it does **not** fix LLM
sampling. So report the primary metric as **"3 independent runs, mean ± range"**
(not "3 seeds") — honest for a stochastic pipeline and consistent with #107's
single-run critique. **>=3 runs per arm.** If cost-prohibitive, state the run
count and reason in the paper.

## Weak-model ablation (#102 directive 2, B(5)) — P1

Re-run all three arms with a weaker base model (`--model`). A persisting arm C −
arm A recall gap, model-independent, is the strongest refutation of "just a
strong LLM." Run after the primary >=3-run pass.

## Optional: share 01a/01b across B and C (review point 4, non-blocking)

To sharpen the "typed-property construction" contrast, copy each run's 01a/01b
outputs from arm C into arm B so both branch from the *same* spec-discovery and
subgraph, fixing the divergence at 01e onward. Not enabled by default (keeps arms
fully independent); enable when isolating the 01e contribution specifically.

## Primary metric + decision rule

Denominator is the #107 population-mapping table (single source). RQ1 primary
metric = **recall on the 15 in-scope H/M/L**, per arm, per severity. Also compute
the **property-only-recoverable set** = findings arm B/C recover that arm A misses.

```
arm A (code-only) recall HIGH  (e.g. >= 12/15)
    -> the spec-anchoring central claim collapses
    -> commit to #106(b) claim-narrowing + #111 deployment reframe (final)

arm A recall LOW and a nameable "property-only-recoverable" set exists
    -> spec-anchoring advantage is clean
    -> a partial generality claim may survive (#106 final scope)
```

## How to run (once wired)

1. Register `03_codeonly` / `03_spec_only` in `config.py` (stubs in `run_arms.py`
   header) and implement the arm A/B queue builder (above).
2. `python experiments/rq1_baselines/run_arms.py --arms A,B,C --runs 3 \
     --sherlock-target <path-to-target-workspace> --model sonnet`
   (model is a `run_phase.py` `--model` flag; the target is passed via
   `SPECA_TARGET_WORKSPACE`; each (arm, run) writes a disjoint output root and
   aborts on a non-zero phase exit.)
3. Score with `--score` (consumes the #107 map to compute per-arm recall).

## Files

- `arms.json` — arm definitions + the output-contract note.
- `prompts/audit_code_only.md` — arm A auditor (no spec/properties).
- `prompts/audit_spec_only.md` — arm B auditor (spec/subgraph, no typed properties).
- `run_arms.py` — orchestration skeleton (wiring + queue builder documented in header).
