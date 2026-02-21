
---
Description: "[WORKER] Perform inline adversarial 3-phase formal audit for a single property (no skill fork)."
Usage: "/03_auditmap_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=1] [OUTPUT_FILE=...]"
Example: "/03_auditmap_worker WORKER_ID=0 QUEUE_FILE=outputs/03_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=1 OUTPUT_FILE=outputs/03_PARTIAL_W0_1700000000_1.json"
Language: English only.
Execution hint: This worker prompt is invoked by the phase-03 async orchestrator. All audit logic is inlined (no skill fork).
---

<task>
  <goal>Execute a complete 3-phase adversarial formal audit for a single property and write the result.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <input type="file" id="context">{{CONTEXT_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    1. Process the item with FULL 3-phase analysis (no shortcuts, no early exits)
    2. Apply adversarial mindset: think like an attacker, not a verifier
    3. Write JSON file to <ref id="results"/> after processing
    4. File MUST be written even if the item is skipped (out-of-scope)
  </critical_requirements>

  <severity_context>
    The `severity` field on each property was assigned using the bug bounty program's
    `severity_classification` criteria (e.g., network impact thresholds, % of validators affected).
    When assessing findings, respect these program-specific severity definitions — do not
    re-classify severity using generic heuristics.
  </severity_context>

  <adversarial_mindset>
    **CRITICAL: Your goal is to FIND vulnerabilities, not prove correctness.**

    **Think like an attacker, not a verifier.**

    Your goal is NOT to prove the code is correct. Your goal is to **find ways to break it**. Ask:
    - "How can I exploit this code?"
    - "What happens if operations occur in unexpected order?"
    - "Can I cause state inconsistency through timing or concurrency?"
    - "What if the cache is stale or inconsistent?"
    - "Can I bypass validation in a specific scenario?"
    - "What happens in unexpected combinations of states?"
    - "What if multiple operations happen concurrently?"

    **DO NOT be satisfied with finding guards. Challenge whether guards are sufficient.**
  </adversarial_mindset>

  <instructions>
    1. **Read Queue**: Read <ref id="queue"/> to get `item_ids` and `context_file` path. Read <ref id="context"/> to get item data (keyed by ID). Extract the single item by looking up the first ID.

    2. **Resolve Code Scope**:
       a. **Pre-resolved (preferred)**: If `item.code_scope.resolution_status == "resolved"` and `item.code_scope.locations` is not empty:
          - Use pre-resolved data from Phase 02c
          - Primary location is first item with `role == "primary"` in locations array
          - Related locations (callers, callees, state management) are available for context
          - Use `item.code_excerpt` if available, which contains all relevant code sections

       b. **Fallback resolution**: If not pre-resolved, use Read/Grep/Glob to find code from `item.text` and `item.assertion`. Derive your own attack approach from the property text and assertion. Think about how to break this property. Extract relevant lines as `code_excerpt`.

       c. **Expand Context for State Analysis**:
          - Use Grep to find related state management code
          - Look for cache structures, concurrent access patterns
          - Include caller/callee context to understand state flow

       d. **Location metadata**: Track for output:
          - `code_scope`: {locations: [{file, symbol, line_range, role}], resolution_status}
          - `code_snippet`: actual code excerpt (primary location or combined from Phase 02c)
          - `state_context`: related state management code (cache, locks, etc.)

       e. **Skip Check**: If `code_scope.resolution_status` is `not_found`/`specification_only`/`out_of_scope`, OR all locations are external (`vendor/`, submodules), OR component mismatch:
          Create result with `classification = "out-of-scope"`, append to `results`, go to step 5.

       **Tool restriction**: Use ONLY Read, Grep, Glob, Write tools for code access.

    3. **3-Phase Adversarial Formal Audit**:

       Execute all three phases sequentially. **DO NOT use early exits or shortcuts.**

       ### Phase 1: Abstract Interpretation with Adversarial Focus

       **Objective:** Identify state anomalies that could be exploited, not just documented.

       1. Use Grep to find related code (callers, state management, caches)
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
       2. Mark as eligible if:
          - Any exploit scenario exists (even if requires specific timing)
          - State inconsistency is possible
          - Guards are incomplete or bypassable
          - Concurrent access can violate invariants
       3. Mark as NOT eligible ONLY if:
          - Completely unreachable from any external interface
          - Explicitly out-of-scope (e.g., execution layer concern in consensus client)
          - Trivially safe with no state or external input (e.g., pure constant getter)
       4. **When in doubt, report it**

    4. **Compress to 6-Field Output**: Map the analysis to the minimal schema:
       - `property_id`
       - `classification` (one of: vulnerability | potential-vulnerability | not-a-vulnerability | informational | out-of-scope)
       - `code_path` (primary location: `file::symbol::Lstart-end`)
       - `proof_trace` (succinct rationale or root cause/proof, 1-3 sentences)
       - `attack_scenario` (only for vulnerability/potential-vulnerability; else "")
       - `checklist_id` (set to property_id for downstream compatibility)

    5. **Write Output**: Write a JSON object with `metadata` and `audit_items` to <ref id="results"/>.

    6. **Confirm**: On stdout, print a one-line summary (<=3 lines total) and `Output File: {{OUTPUT_FILE}}`.
  </instructions>

  <output_schema>
    Write a single JSON object with two keys:
    - "metadata": keep the existing metadata structure (phase, worker_id, batch_index, item_count, timestamp, processed_ids, etc.) unchanged.
    - "audit_items": an array of result rows. Each row MUST contain ONLY the following keys, nothing else:
      1) "property_id"       -> the property_id string
      2) "classification"    -> one of: vulnerability | potential-vulnerability | not-a-vulnerability | informational | out-of-scope
      3) "code_path"         -> string like "path/to/file.go::FuncName::L22-33" (primary location)
      4) "proof_trace"       ->
         - if classification is vulnerability or potential-vulnerability: concise root cause statement + short proof / why the guard fails (1-3 sentences)
         - otherwise: concise rationale why it is safe or out-of-scope (1-3 sentences)
      5) "attack_scenario"   ->
         - if vulnerability/potential-vulnerability: one concrete exploit path (1-2 sentences)
         - otherwise: empty string ""
      6) "checklist_id"      -> the property_id string (for downstream compatibility)
    - Do NOT emit any other fields (no severity, confidence, bug_bounty_eligible, phases, state_context, summaries, recommendations, counts, or headers).
    - Preserve JSON ordering above for readability.
  </output_schema>

  <quality_gates>
    **Before writing output, verify:**

    1. **Field whitelist**: Every audit_items element has exactly the 6 allowed keys (property_id, classification, code_path, proof_trace, attack_scenario, checklist_id). No extras.
    2. **Non-empty rationale**: proof_trace non-empty (<= 3 sentences). attack_scenario non-empty only for vulnerability/potential-vulnerability; otherwise exactly "".
    3. **Code path present**: code_path includes file, symbol (if available), and line range e.g., `beacon-chain/core/peerdas/reconstruction.go::ReconstructDataColumnSidecars::L31-122`.
    4. **Classification sanity**: use allowed set only.
    5. **Metadata preserved**: metadata object is still included and unchanged except for fields you legitimately update (e.g., timestamp, processed_ids).
    6. **All phases executed**: Every phase (1, 2, 3, 3.5) must have been considered. No early exits.
  </quality_gates>

  <anti_patterns>
    **AVOID these common mistakes:**

    - "This code has validation, so it's safe" -> "Is validation sufficient for ALL scenarios?"
    - "No counterexample found, mark as safe" -> "Why couldn't I find one? Is it complex?"
    - "Code looks simple, skip detailed analysis" -> "Complex bugs hide in simple code"
    - "Early exit to save tokens" -> "Full analysis to find real bugs"
    - "Validation exists, therefore safe" -> "How can I exploit this despite the guards?"
    - "Guards exist, skip proving they're sufficient" -> "What state combinations can cause issues?"
  </anti_patterns>
</task>
