---
name: formal-audit-phase1
description: Perform Phase 1 (Abstract Interpretation) for a checklist item.
allowed-tools: Read, Grep, Glob, Write
context: fork
---

# SKILL: Formal Static Audit Phase 1 (Abstract Interpretation)

## Mindset
You are an **Abstract Interpretation Specialist**. Think in terms of ranges, sets, and potential states.

## Goal
Analyze the code scope using abstract interpretation to identify possible state-space anomalies.

## Input
A JSON object representing a single audit item:

```json
{
  "check_id": "...",
  "checklist_item": { ... },
  "code_scope": {
    "file": "...",
    "function": "...",
    "line_range": "..."
  },
  "code_excerpt": "..."
}
```

## Procedure
1. Identify all variables within the Code Scope.
2. For each variable, determine its abstract domain (ranges, sets, etc.).
3. Trace how operations transform these abstract domains.
4. Look for anomalies (overflow, null, unbounded growth).

## Output Format
Return a JSON object:

```json
{
  "phase1_abstract_interpretation": {
    "summary": "...",
    "state_anomalies_found": []
  }
}
```
