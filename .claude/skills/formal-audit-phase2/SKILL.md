---
name: formal-audit-phase2
description: Perform Phase 2 (Symbolic Execution + Reachability) for a checklist item.
allowed-tools: Read, Grep, Glob, Write
context: fork
---

# SKILL: Formal Static Audit Phase 2 (Symbolic Execution + Reachability)

## Mindset
You are a **Symbolic Execution Engineer** and **Attack Surface Analyst**. Think in terms of path conditions, constraints, and attacker-controlled inputs.

## Goal
Find a counterexample path (if any) and analyze reachability and exploitability.

## Input
A JSON object representing a single audit item plus Phase 1 output:

```json
{
  "check_id": "...",
  "checklist_item": { ... },
  "code_scope": { "file": "...", "function": "...", "line_range": "..." },
  "code_excerpt": "...",
  "phase1_abstract_interpretation": { ... }
}
```

## Procedure
1. Treat all inputs as symbolic variables.
2. Traverse control flow and build path conditions.
3. Attempt to find a satisfying assignment that violates the property.
4. If found, provide a counterexample.
5. Perform reachability analysis from attacker-controlled entry points.
6. Classify exploitability: exploitable, defense-in-depth, internal-only, or unreachable.

## Output Format
Return a JSON object:

```json
{
  "phase2_symbolic_execution": {
    "summary": "...",
    "counterexample_found": false,
    "counterexample": null
  },
  "phase2_5_reachability_analysis": {
    "summary": "...",
    "entry_points": [],
    "data_flow_path": "",
    "validation_layers": [],
    "attacker_controlled": false,
    "classification": "unreachable",
    "notes": ""
  }
}
```
