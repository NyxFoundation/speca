# RULES.md — Evidence over testimony

The single, machine-checkable norm for every human and every AI session in this
repo. CLAUDE.md, the PR template, and the issue templates all point here. If a
rule here conflicts with a longer doc (LANDMINES.md, SESSION-START.md), **this
file wins** — those are background; this is the contract.

## The principle

> **artifact (the raw execution result) > testimony (a claim that it happened).**

"I fixed it", "the test passes", "verified against the schema" are testimony —
the narrator's story. They are **not** admissible. The only admissible ground
for a claim is a raw command output captured **in the same turn as the claim**,
plus a recipe a reviewer can re-run to regenerate it themselves.

## The six rules

1. **Same-turn fresh evidence only.** Paste the real command output immediately
   before writing "done". Never ground a claim on memory or a previous turn's
   result — re-run it now.
2. **Unverified may be written as unverified.** "I don't know" / "not checked
   yet" is a valid, non-failing answer. It is always preferred over a
   confident claim you cannot back. Honesty is never penalized; unsupported
   confidence always is.
3. **Quote the raw log, not a summary.** Not "confirmed X" — paste the log line
   that shows X. A claim keyword with no adjacent raw output is rejected.
4. **Refute, don't confirm.** The verification question is never "is this
   right?" It is "find the evidence that breaks this claim; if you find none,
   only then submit." Red-before-green (a fix's test must fail on the pre-fix
   code) is one instance of refutation.
5. **Cross-check from outside the author's context.** An independent pass reads
   only (claim, re-run recipe) — never the author's narrative — re-executes,
   and reports only mismatches. The writer's story must not reach the checker.
6. **Split tasks small.** A 100+-file PR (see #118) widens the gap between the
   AI's internal picture and the real code. Below the size gate, or justify the
   split explicitly.

## The Evidence Block (the machine-readable unit)

Every claim of the form "verified / passes / done" MUST appear as this block —
prose claims are rejected by `scripts/evidence_check.py`:

```
<!-- EVIDENCE claim="paper_metrics counts confirmed=7 on real lodestar 04" -->
​```
$ python3 experiments/paper_metrics/build_population_table.py --p04 cli/test/fixtures/sherlock-rq1/lodestar_fusaka/04_PARTIAL_*.json
{"adjudicated_reviewed": 37, "confirmed": 7, "disputed": 0}
​```
<!-- RERUN: python3 experiments/paper_metrics/build_population_table.py --p04 cli/test/fixtures/sherlock-rq1/lodestar_fusaka/04_PARTIAL_*.json EXPECT "confirmed": 7 -->
```

Three parts, or it is testimony, not evidence:
- **claim** — the exact assertion.
- **raw log** — verbatim tool output in a fenced block (rule 3).
- **RERUN … EXPECT …** — a command the checker runs itself, and the substring it
  must find (rules 1 & 5: freshness stops mattering when the verifier
  regenerates the output).

When you have not verified something, say so with a first-class marker instead
of inventing evidence (rule 2):

```
<!-- UNVERIFIED: did not run property_type_precision — no real 01e in the fixture to join property_id -> type -->
```

`UNVERIFIED` blocks always pass the gate. An unsupported `VERIFIED`-style claim
never does.

## Enforcement (why this file is not itself testimony)

A norm doc alone gets ignored — that is the failure this repo keeps repeating.
So the rules above are enforced mechanically, not by good intentions:

| Rule | Mechanism | File |
|------|-----------|------|
| 1, 3, 5 | `evidence_check.py`: every VERIFIED claim needs an adjacent raw log; every RERUN is **re-executed** and matched against EXPECT | `scripts/evidence_check.py` |
| 2 | `UNVERIFIED` is a passing state; only unsupported confidence fails | same |
| 4 | verification prompts are refute-framed; bug fixes carry red-before-green output | PR template |
| 6 | size gate: changed-files over the threshold fails without a `SPLIT-JUSTIFIED` marker | `evidence_check.py --changed-files` |

CI runs `evidence_check.py` on every PR body. The workflow is shipped at
`ci/evidence-check.yml`; a maintainer with `workflow` scope installs it to
`.github/workflows/` (the authoring token here lacks that scope). Until then the
gate still runs locally / as a pre-commit / manually: `python3
scripts/evidence_check.py --body <pr_body.md> --changed-files <N>`.

The genuinely non-deterministic claims (e.g. an LLM audit result) that CI cannot
re-run are handed to an independent cross-check pass (rule 5), never self-signed.
