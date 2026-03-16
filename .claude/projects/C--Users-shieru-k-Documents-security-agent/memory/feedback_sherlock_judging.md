---
name: Sherlock judging criteria filter
description: Only report bugs that are realistic and exploitable under normal conditions — extreme edge cases and admin-dependent bugs are rejected by Sherlock judges
type: feedback
---

Do NOT report bugs that require:
- Extreme/unrealistic parameter values (u64::MAX, 0 decimals, etc.)
- Admin misconfiguration or admin error as a precondition
- Economically insignificant impact (1 wei, dust amounts)
- Conditions that would never occur in normal protocol operation

**Why:** Sherlock contest judges reject findings that depend on unrealistic conditions. Only findings that can occur under normal market conditions with realistic parameters are accepted as valid Medium/High.

**How to apply:** When filtering agent results, ask: "Would this happen on mainnet with real users and real market conditions?" If not, skip it.
