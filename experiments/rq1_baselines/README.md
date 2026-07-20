# RQ1 Controlled Baselines (issue #102)

Decision experiment for reviewer comments **#1756A(1)** (missing controlled
baseline) and **#1756B(5)** (framework vs. base-model). Its result gates the
paper's framing decisions in #106 (generality) and #111 (deployment reframe),
so it runs **first**.

> Status: **design + scaffold**. The arm prompts and protocol below are
> complete and ready. The runner (`run_arms.py`) is a skeleton that documents
> the exact wiring into `scripts/run_phase.py`; it needs the two variant audit
> phases registered in `scripts/orchestrator/config.py` and **one smoke-test
> run** before its numbers can be trusted. Nothing here has been executed yet
> (no compute budget / findings data in this environment).

## Three arms — vary only the front-end, hold the audit/review constant

The pipeline is `01a → 01b → 01e → 02c → 03 → 04`. Only the property front-end
(spec discovery → typed property generation → code pre-resolution) is varied;
the audit reasoning and the Phase-04 review gates are held constant so any
delta is attributable to the property scaffolding, not to a different judge.

| Arm | Input given to the auditor | Phases run | Audit prompt |
|-----|----------------------------|------------|--------------|
| **A. code-only-LLM** | target code only (no spec, no properties) | 03′ → 04 | `prompts/audit_code_only.md` |
| **B. spec-only-no-properties** | spec text + subgraph, **no typed properties** | 01a → 01b → 03″ → 04 | `prompts/audit_spec_only.md` |
| **C. SPECA full** | typed properties + resolved code scope | 01a → 01b → 01e → 02c → 03 → 04 | `prompts/03_auditmap_worker_inline.md` (unchanged) |

`03′` and `03″` are the two variant audit prompts in `prompts/` here. `04`
(review) is the **unmodified** production `prompts/04_review_worker.md` for all
three arms, so false-positive filtering is identical across arms.

## Held constant (must not vary across arms)

- Base model (default `sonnet`); recorded per run.
- Target repository + commit — the same `outputs/TARGET_INFO.json` for all arms.
- Sherlock scope (`outputs/BUG_BOUNTY_SCOPE.json`), including `trust_assumptions`
  and severity thresholds.
- Phase-04 review (3 gates) and severity calibration.
- Worker count and compute budget per arm.

## Seed protocol (#102 directive 1)

- **≥3 seeds per arm.** A seed pins `SPECA_RUN_ID` (see CLAUDE.md) so the
  timestamp+nonce is deterministic; arms/seeds write to disjoint output roots.
- Report the **primary metric as mean ± range (or SD)** across seeds. A
  single-run comparison will be attacked at the next review (the current paper
  is single-run — see #107). If 3 seeds is cost-prohibitive, state the seed
  count and the reason in the paper.

## Weak-model ablation (#102 directive 2, B(5)) — P1

Re-run all three arms with a **weaker base model** (set `arm.model`). If the
framework's contribution (arm C − arm A recall gap) persists model-independently,
that is the strongest refutation of "the framework is just a strong LLM." Run
after the primary 3-seed pass.

## Primary metric + decision rule

Denominator is the #107 population-mapping table (single source). RQ1 primary
metric = **recall on the 15 in-scope H/M/L findings**, per arm, with per-severity
breakdown. Also compute the **"property-only-recoverable" set** = findings arm
B/C recover that arm A misses (names the payoff of spec anchoring, A(1)).

```
arm A (code-only) recall HIGH  (e.g. >= 12/15)
    -> the spec-anchoring central claim collapses
    -> commit to #106(b) claim-narrowing + #111 deployment reframe (final)

arm A recall LOW and a nameable "property-only-recoverable" set exists
    -> spec-anchoring advantage is clean
    -> a partial generality claim may survive (#106 final scope)
```

## How to run (once wired)

1. Register the two variant phases in `config.py` (see `run_arms.py` header for
   the exact `PhaseConfig` stubs — `03_codeonly` and `03_spec_only`, each
   `depends_on` reduced accordingly and `input_patterns` pointing at the target
   workspace / `01b_PARTIAL_*.json` respectively).
2. `python experiments/rq1_baselines/run_arms.py --arms A,B,C --seeds 3 \
     --target <sherlock-target> --model sonnet`
3. Score with `--score` (consumes the #107 mapping to compute per-arm recall).

## Files

- `arms.json` — arm definitions (phases, prompt, model, seeds).
- `prompts/audit_code_only.md` — arm A auditor (no spec/properties).
- `prompts/audit_spec_only.md` — arm B auditor (spec/subgraph, no typed properties).
- `run_arms.py` — orchestration skeleton (wiring documented in its header).
