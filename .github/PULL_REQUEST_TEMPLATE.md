<!--
Thanks for contributing to SPECA! A few quick notes:
- All PRs require approval from @grandchildrice (enforced via CODEOWNERS).
- Please keep changes focused; pipeline phases are deliberately decoupled.
- Our bot is allergic to scope creep — split unrelated changes into separate PRs.

EVIDENCE OVER TESTIMONY (see RULES.md). "It works" / "tests pass" is testimony
and is not admissible. Back every such claim with an Evidence Block — a raw log
plus a RERUN recipe that CI re-executes for itself. Honest "UNVERIFIED" always
passes; an unsupported claim never does. `evidence-check` CI runs on this body.

REVIEWER'S ONE CHECK (bug fixes): does the added/updated test FAIL on the pre-fix
code? If it cannot be shown red before the fix, it verifies nothing (see #134:
CI green, feature broken). Red-before-green is one instance of RULES.md rule 4
(refute, don't confirm) — fill the evidence box below.
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

## Test plan — Evidence Blocks (RULES.md)

<!--
Do NOT write "tests pass". Paste an Evidence Block per claim: the raw log, and a
RERUN line CI re-executes. What you cannot verify, mark UNVERIFIED (that passes).
Format (the HTML comments are the machine-readable part):

<!-- EVIDENCE claim="pytest suite is green" -->
​```
$ uv run python3 -m pytest tests/ -q
823 passed, 2 skipped
​```
<!-- RERUN: uv run python3 -m pytest tests/ -q EXPECT passed -->
-->

<!-- EVIDENCE claim="..." -->
```
# paste the verbatim command + output
```
<!-- RERUN: <command> EXPECT <substring> -->

<!-- UNVERIFIED: <anything you did not check — this is allowed and preferred over guessing> -->

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
