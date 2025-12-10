

---
Description: Review and validate existing @audit annotations listed in security-agent/outputs/03_AUDITMAP.json.
Usage: `/04_review`
Example: `/04_review`
---

**Always use /serena for these development tasks to maximize token efficiency:**



# 🎯 Goal
For every entry recorded in `security-agent/outputs/03_AUDITMAP.json`, decide with rigorous reasoning whether the referenced `@audit` remains a real, exploitable issue. When disproved, transform the source comment into `@audit-ok` with a brief rationale and remove the corresponding entry from `03_AUDITMAP.json`. When confirmed (or partially confirmed), keep `@audit`, expand insight, and categorise the exact risk while updating the map item.

Finally, synchronise results back into `security-agent/outputs/03_AUDITMAP.json`.

# 📥 Input
1. Audit map:         `security-agent/outputs/03_AUDITMAP.json`
2. Checklist context: `security-agent/outputs/02_CHECKLIST.json` (`ok_if` guidance)
3. Source code (rec.): referenced by each audit entry
4. Project spec:      `security-agent/outputs/01_SPEC.json`
5. External context:  Use web search to locate related PRs or documentation and weigh them alongside `01_SPEC.json` when interpreting intent.

# 📤 Output
1. **Inline updates** — rewrite the original `@audit` comment in-place as an `@audit-ok` comment that records both the former concern and the guard that resolves it:
   ```solidity
   // @audit-ok Reentrancy: external call precedes state update
   // ↳ Guard: nonReentrant modifier blocks reentry, execution stays single-pass
   ```
   When a comment becomes `@audit-ok`, delete the associated item from `03_AUDITMAP.json`.

2. **Updated** `03_AUDITMAP.json`

   ```jsonc
   {
     "audit_items": [
       {
         "id": "03523523",
         "file": "src/Vault.sol",
         "line": 152,
         "snippet": "call{value: amount}();",
         "risk_category": "Reentrancy",
         "description": "External transfer before buffer update; nonReentrant missing",
         "status": "Vuln",               // or "ok"
         "proof_trace": [
           "Vault.withdraw (L140-170)",
           "↳ _transfer (L95-112)"
         ],
         "review_round": 2
       }
     ],
     "summary": {
       "rounds": 4,
       "total_audit_flags": 21,
       "high_risk_hotspots": ["src/Vault.sol:withdraw"],
       "next_focus": "Permission bypass on src/Admin.rs:setConfig"
     }
   }
   ```

# 🧮 Evaluation Framework  (apply to every finding)

1. **Core-Logic** — depth ≤ 2 & critical TVL / mint / pricing paths
2. **Permissionless Reachability** — prove lack of owner / role guard
3. **Guard Bypass & State Reachability** — enumerate *all* checks, find gaps
4. **Non-self Attack** — impact > attacker alone
5. **Bug Bounty Scope** — verify in-scope via `security-agent/outputs/01_BOUNTY_GUIDELINE.md` (if exists)

While assessing "ok" cases, consult the applicable `ok_if` rationale in `02_CHECKLIST.json` and ensure the justification aligns with its acceptance conditions.

# 🔍 Review Procedure

```
LOAD audit_items FROM security-agent/outputs/03_AUDITMAP.json ORDERED BY file→line:
    ENSURE the command was invoked with no arguments; rely exclusively on the audit map entry.
    1. Re-open the source location (file and line) and confirm the @audit context.
    2. Derive execution path (AST and callgraph) and record a line-number trace in proof_trace.
    3. Cross-reference `02_CHECKLIST.json.ok_if` for matching categories; if all acceptance criteria are met, proceed toward @audit-ok.
    4. Research spec alignment: run a web search for related PRs or product documentation and combine those findings with `01_SPEC.json` to understand expected behaviour.
    5. Apply Evaluation Framework (§🧮) and compare to similar bugs in bugs_*.json to note variant attacks.
    6. Decide:
        a) Exploitable ⇒ keep @audit, enrich description, set status="Vuln" (or "Needs-Review"), retain entry in 03_AUDITMAP.json.
        b) Non-exploitable ⇒ transform comment to @audit-ok, set status="ok", remove the audit item from 03_AUDITMAP.json.
    7. Update security-agent/outputs/02_ORDER.json.review_rounds++
REPEAT until no unchecked audit_items remain.
```

# 🧠 Required Deep-Dive Tests

* **Step-by-step execution trace** — include in `proof_trace` (file:line)
* **Logical contradiction check** — ensure premises stay jointly satisfiable
* **Guard enumeration** — list modifiers / require / ACL that could block
* **Independent verification** — rely on own reading, not external scanner verdicts
* **Exploitability demonstration** — if doubtful, mark *Need further investigation*

# 📝 Comment Syntax (strict)

```rust
// @audit-ok <Category>: <Prior concern summary>
// ↳ Guard: <Specific control that neutralises the concern>
```

# 🛠️ Methodology

* **Depth-first within function**: validate inner-most dangerous ops first.
* Use *internal* chain-of-thought; divulge **only** final comments and JSON.
* Limit new annotations per run to 15 for readability.

# ⛔ Constraints

* Do not alter executable logic.
* No duplicate audit entries for identical location.
* Validate JSON and timestamps (RFC3339) before write.

# ✅ Success Criteria

* Every prior @audit reviewed once.
* `03_AUDITMAP.json` parses and mirrors code state (with completed items removed).
* High-risk hotspots surfaced.
* `summary.next_focus` suggests concrete next steps.
