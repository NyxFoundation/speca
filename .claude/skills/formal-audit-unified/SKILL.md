---
name: formal-audit-adversarial
description: Perform adversarial three-phase formal audit with attacker mindset for a checklist item.
allowed-tools: Read, Grep, Glob, Write, mcp__filesystem__read_text_file, mcp__filesystem__search_files
context: fork
---

# SKILL: Adversarial Formal Static Audit (3 Phases)

## Goal
Perform a complete three-phase formal audit with an **attacker mindset** to identify exploitable vulnerabilities, not just verify correctness.

## Core Mindset

**Think like an attacker, not a verifier.**

Your goal is NOT to prove the code is correct. Your goal is to **find ways to break it**. Ask:
- "How can I exploit this?"
- "What happens in unexpected combinations of states?"
- "Can I bypass this check in a specific scenario?"
- "What if multiple operations happen concurrently?"

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

Execute all three phases sequentially. **DO NOT use early exits or shortcuts.**

### Phase 1: Abstract Interpretation with Adversarial Focus

**Objective:** Identify state anomalies that could be exploited, not just documented.

1. Use `mcp__filesystem__search_files` to find related code (callers, state management, caches)
2. Identify variables and their abstract domains (ranges, sets, **state machines**)
3. **Focus on state transitions**: How does state change over time? Can state become inconsistent?
4. Look for:
   - **Cache inconsistencies**: Is cached data invalidated correctly?
   - **TOCTOU (Time-of-Check-Time-of-Use)**: Can state change between check and use?
   - **Unordered operations**: Does order matter (e.g., Go map iteration)?
   - **Concurrent access**: Can multiple goroutines/threads cause race conditions?
   - **Overflow, null, unbounded growth**
5. **Output**: List ALL potential state anomalies, even if guards exist

**CRITICAL**: Do NOT skip this phase even if code looks simple. Complex bugs hide in simple-looking code.

### Phase 2: Symbolic Execution with Exploit Construction

**Objective:** Construct concrete exploit scenarios, not just find counterexamples.

1. Treat inputs as symbolic variables
2. Build path conditions through control flow
3. **Actively try to construct exploits**:
   - Can you craft inputs that bypass validation?
   - Can you trigger the anomalies found in Phase 1?
   - Can you exploit timing windows (TOCTOU)?
   - Can you cause state inconsistency through specific operation sequences?
4. **For each anomaly from Phase 1**, attempt to build a concrete attack scenario
5. Analyze reachability from attacker-controlled entry points (P2P, RPC, user input)
6. Classify exploitability:
   - **exploitable**: Attacker can trigger from external interface
   - **defense-in-depth**: Requires bypassing other layers, but theoretically possible
   - **internal-only**: Only reachable from trusted code paths
   - **unreachable**: No path exists

**CRITICAL**: "No counterexample found" does NOT mean safe. It may mean the exploit is complex or requires specific timing. Document this uncertainty.

### Phase 3: Invariant Analysis with Skepticism

**Objective:** Determine if guards are SUFFICIENT, not just present.

1. **DO NOT assume guards are sufficient just because they exist**
2. For each guard/validation:
   - Does it cover ALL attack scenarios from Phase 2?
   - Can it be bypassed in specific states or timing?
   - Does it protect against concurrent access?
   - Does it validate ALL relevant properties (not just input values)?
3. **Check for logic gaps**:
   - Is validation applied consistently across all code paths?
   - Are there edge cases where validation is skipped?
   - Does the guard protect the ACTUAL invariant, or just a proxy?
4. **Attempt to prove the property holds**, but:
   - If proof fails, document why
   - If proof succeeds, **challenge it**: What assumptions did you make? Are they valid?

### Phase 3.5: Scope Filtering with Conservative Bias

**Objective:** Determine bug bounty eligibility with a **bias toward reporting**.

1. **Default to "eligible" unless clearly out-of-scope**
2. Mark as `bug_bounty_eligible: true` if:
   - Any exploit scenario exists (even if requires specific timing)
   - State inconsistency is possible
   - Guards are incomplete or bypassable
   - Concurrent access can violate invariants
3. Mark as `bug_bounty_eligible: false` ONLY if:
   - Completely unreachable from any external interface
   - Explicitly out-of-scope (e.g., execution layer concern in consensus client)
   - Trivially safe with no state or external input (e.g., pure constant getter)
4. **When in doubt, report it**

## Output Format

Return a **detailed** JSON object with concrete findings:

```json
{
  "phase1_abstract_interpretation": {
    "summary": "Detailed 2-4 sentence summary of state analysis",
    "state_anomalies_found": ["specific anomaly 1", "specific anomaly 2"],
    "cache_analysis": "How is state/cache managed? Can it become inconsistent?",
    "concurrency_analysis": "Can concurrent access cause issues?"
  },
  "phase2_symbolic_execution": {
    "summary": "Detailed 2-4 sentence summary of exploit construction",
    "counterexample_found": true/false,
    "counterexample": "Concrete exploit scenario if found",
    "attack_scenarios": ["scenario 1", "scenario 2"],
    "timing_dependencies": "Does exploit require specific timing or race conditions?"
  },
  "phase2_5_reachability_analysis": {
    "summary": "Detailed 2-4 sentence summary of reachability",
    "entry_points": ["entry1", "entry2"],
    "attacker_controlled": true/false,
    "classification": "exploitable/defense-in-depth/internal-only/unreachable",
    "attack_surface": "Describe how attacker can reach this code"
  },
  "phase3_invariant_proving": {
    "summary": "Detailed 2-4 sentence summary of invariant analysis",
    "proof_successful": true/false,
    "guard_identified": "Specific guard mechanism",
    "guard_sufficiency": "Is the guard sufficient? What gaps exist?",
    "edge_cases": ["edge case 1", "edge case 2"]
  },
  "phase3_5_scope_filtering": {
    "bug_bounty_eligible": true/false,
    "reason": "Detailed reason for eligibility decision",
    "recommendation": "Concrete recommendation for fix",
    "severity_estimate": "Critical/High/Medium/Low based on exploitability"
  },
  "final_classification": "vulnerability/not-a-vulnerability/informational/out-of-scope"
}
```

## Key Differences from Original

1. **NO Early Exits**: Every phase must be executed fully
2. **Adversarial Mindset**: Explicitly instructed to think like an attacker
3. **State Focus**: Emphasis on cache, TOCTOU, concurrency, ordering
4. **Detailed Output**: Require concrete scenarios, not just summaries
5. **Conservative Filtering**: Bias toward reporting, not dismissing
6. **Skepticism of Guards**: Guards must be proven sufficient, not assumed

## Anti-Patterns to Avoid

- ❌ "Validation exists, therefore safe"
- ❌ "No counterexample found, therefore safe"
- ❌ "Code looks simple, skip detailed analysis"
- ❌ "Guards exist, skip proving they're sufficient"
- ✅ "How can I exploit this despite the guards?"
- ✅ "What state combinations can cause issues?"
- ✅ "Can I trigger this through timing or concurrency?"
