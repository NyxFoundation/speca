---
name: formal-audit-phase3
description: Perform Phase 3 (Invariant Proving + Scope Filtering) for a checklist item.
allowed-tools: Read, Grep, Glob, Write
context: fork
---

# SKILL: Formal Static Audit Phase 3 (Invariant Proving + Scope Filtering)

## Mindset
You are a **Theorem Proving Specialist** and **Bug Bounty Triager**. Think in terms of mathematical proofs and bounty eligibility criteria.

## Goal
Prove the invariant if no counterexample was found, or determine bounty eligibility if found.

## Input
A JSON object representing a single audit item plus Phase 1+2 outputs:

```json
{
  "check_id": "...",
  "checklist_item": { ... },
  "code_scope": { "file": "...", "function": "...", "line_range": "..." },
  "code_excerpt": "...",
  "phase1_abstract_interpretation": { ... },
  "phase2_symbolic_execution": { ... },
  "phase2_5_reachability_analysis": { ... }
}
```

## Procedure
1. If no counterexample, attempt to prove the property holds for all paths.
2. If a counterexample exists, determine bug bounty eligibility based on scope.
3. Record final eligibility decision.

## Output Format
Return a JSON object:

```json
{
  "phase3_invariant_proving": {
    "summary": "...",
    "proof_successful": false,
    "guard_identified": null
  },
  "phase3_5_scope_filtering": {
    "bug_bounty_eligible": false,
    "reason": "...",
    "recommendation": "",
    "notes": ""
  }
}
```
