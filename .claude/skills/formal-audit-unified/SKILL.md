---
name: formal-audit-unified
description: Perform unified three-phase formal audit (Abstract Interpretation → Symbolic Execution → Invariant Proving) for a checklist item.
allowed-tools: Read, Grep, Glob, Write, mcp__filesystem__read_text_file, mcp__filesystem__search_files
context: fork
---

# SKILL: Unified Formal Static Audit (3 Phases)

## Goal
Perform a complete three-phase formal audit in a single context to minimize token overhead.

## Input
A JSON object representing a single audit item:

```json
{
  "check_id": "...",
  "checklist_item": {
    "property_id": "...",
    "description": "...",
    "graph_element_under_test": "..."
  },
  "code_scope": {
    "file": "...",
    "function": "...",
    "line_range": "..."
  },
  "code_excerpt": "..."
}
```

## Procedure

Execute all three phases sequentially in this single context:

### Phase 1: Abstract Interpretation
1. Use `mcp__filesystem__search_files` to find related code (callers, dependencies) if needed
2. Identify variables within code scope and their abstract domains (ranges, sets)
3. Trace how operations transform these domains
4. Look for state anomalies (overflow, null, unbounded growth)
5. **Early Exit Check**: If code is trivially safe (e.g., simple getter, constant return, no external input), mark as `trivially_safe=true` and skip to Phase 3 with minimal analysis

### Phase 2: Symbolic Execution + Reachability
**Skip this phase if `trivially_safe=true` from Phase 1**

1. Treat inputs as symbolic variables
2. Build path conditions through control flow
3. Attempt to find assignment that violates the property (counterexample)
4. Analyze reachability from attacker-controlled entry points
5. Classify exploitability: exploitable, defense-in-depth, internal-only, or unreachable
6. **Early Exit Check**: If no counterexample found and code has strong guards, mark as `verified_safe=true` and skip detailed proving in Phase 3

### Phase 3: Invariant Proving + Scope Filtering
**Use simplified analysis if `trivially_safe=true` or `verified_safe=true`**

1. If `trivially_safe=true`: Record as safe without detailed proving
2. If `verified_safe=true`: Record guards as sufficient proof
3. If no counterexample: attempt to prove property holds for all paths
4. If counterexample exists: determine bug bounty eligibility based on scope
5. Record final eligibility decision

## Output Format

Return a **compact** JSON object containing only essential findings:

```json
{
  "phase1_abstract_interpretation": {
    "summary": "Brief 1-2 sentence summary",
    "state_anomalies_found": ["anomaly1", "anomaly2"]
  },
  "phase2_symbolic_execution": {
    "summary": "Brief 1-2 sentence summary",
    "counterexample_found": false,
    "counterexample": null
  },
  "phase2_5_reachability_analysis": {
    "summary": "Brief 1-2 sentence summary",
    "entry_points": ["entry1"],
    "attacker_controlled": false,
    "classification": "unreachable"
  },
  "phase3_invariant_proving": {
    "summary": "Brief 1-2 sentence summary",
    "proof_successful": false,
    "guard_identified": null
  },
  "phase3_5_scope_filtering": {
    "bug_bounty_eligible": false,
    "reason": "Brief reason",
    "recommendation": ""
  }
}
```

## Optimization Guidelines

- **Be concise**: Use 1-2 sentence summaries, not paragraphs
- **Omit verbose explanations**: Only include when counterexample found
- **Use minimal MCP queries**: Read only what's necessary
- **Use `head`/`tail` parameters**: Don't read entire files if partial context suffices
- **Early termination**: Implement early exit checks at each phase to skip unnecessary analysis
- **Trivially safe cases**: Simple getters, constant returns, or pure functions with no external input should be marked as trivially safe
- **Verified safe cases**: Code with strong input validation and clear guards can skip detailed invariant proving
