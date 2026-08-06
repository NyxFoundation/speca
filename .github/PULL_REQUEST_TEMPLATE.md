<!--
Thanks for contributing to SPECA! A few quick notes:
- All PRs require approval from @grandchildrice (enforced via CODEOWNERS).
- Please keep changes focused; pipeline phases are deliberately decoupled.
- Our bot is allergic to scope creep — split unrelated changes into separate PRs.

REVIEWER'S ONE CHECK (bug fixes): does the added/updated test FAIL on the pre-fix
code? If it cannot be shown red before the fix, it verifies nothing (see #134:
CI green, feature broken). This is the single acceptance gate — fill the
"red-before-green evidence" box below.
-->

## Summary

<!-- 1–3 bullets describing what changed and why. Focus on the motivation, not the diff. -->
-

## Type of change

<!-- Check all that apply -->
- [ ] Bug fix
- [ ] New feature / enhancement
- [ ] Refactor / cleanup (no behavior change)
- [ ] Documentation / benchmarks
- [ ] Pipeline phase change (which phase: ___)
- [ ] CI / tooling

## Test plan

<!-- How was this verified? Concrete commands and expected output, ideally. -->
- [ ] `uv run python3 -m pytest tests/ -v --tb=short` passes
- [ ]

### Red-before-green evidence (required for Bug fix)

<!--
The acceptance gate. A test that passes on the pre-fix code proves nothing (#134
shipped CI-green but broken because its fixture never exercised the failing
case). So SHOW the test failing first:
  1. stash/revert only the fix (keep the test), or check out the pre-fix commit
  2. run the specific test — it must FAIL on the real failing case
  3. re-apply the fix — it passes
Or reproduce the bug by injection, as done well in #120. Paste the pre-fix
failure below (the actual failing assertion, not "trust me").
-->
- [ ] The covering test was observed **RED on the pre-fix code**, then GREEN after the fix (evidence below), OR this PR has no bug-fix behavior change (feature/docs/refactor).

```
# pre-fix run — paste the FAILING output here (assertion + expected/actual)
```

## Schema / contract impact

<!-- Did you change inter-phase data contracts (scripts/orchestrator/schemas.py)? If yes, list the affected phases. -->
- [ ] No schema or contract changes
- [ ] Schema changed; affected phases: ___

## Related issues / context

<!-- Closes #N, refs #M, link to spec section, or paper section. -->

## Reviewer notes

<!-- Anything you'd like the reviewer to look at first; tradeoffs you considered; alternatives you rejected. -->
