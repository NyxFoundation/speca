
---
Description: [WORKER] Invoke the adversarial formal-audit skill for a batch of items using MCP tools.
Usage: `/03_auditmap_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]`
Example: `/03_auditmap_worker WORKER_ID=0 QUEUE_FILE=outputs/03_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=5 OUTPUT_FILE=outputs/03_PARTIAL_W0_1700000000_1.json`
Language: English only.
Execution hint: This worker prompt is invoked by the phase-03 async orchestrator with MCP tools enabled.
---

<task>
  <goal>For each item in the batch, resolve code scope and invoke /formal-audit-adversarial skill with attacker mindset.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <input type="file" id="context">{{CONTEXT_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    1. Process ALL items in the batch with FULL analysis (no shortcuts)
    2. Apply adversarial mindset: think like an attacker, not a verifier
    3. Write JSON file to <ref id="results"/> after processing ALL items
    4. File MUST be written even if some items are skipped
  </critical_requirements>

  <adversarial_mindset>
    **CRITICAL: Your goal is to FIND vulnerabilities, not prove correctness.**
    
    For each item, ask yourself:
    - "How can I exploit this code?"
    - "What happens if operations occur in unexpected order?"
    - "Can I cause state inconsistency through timing or concurrency?"
    - "What if the cache is stale or inconsistent?"
    - "Can I bypass validation in a specific scenario?"
    
    **DO NOT be satisfied with finding guards. Challenge whether guards are sufficient.**
  </adversarial_mindset>

  <optimization_strategy>
    **BALANCED APPROACH: Thoroughness over Speed**
    
    **1. Batch Skill Invocation** (for efficiency):
    - Group items by file/component when possible
    - Invoke skill once per group to reduce overhead
    - BUT: Do NOT sacrifice analysis depth for speed
    
    **2. Context Optimization**:
    - Group by file to maximize cache hits
    - Reuse context across related items
    - Keep common definitions in same conversation
    
    **3. NO Early Exits**:
    - Every item MUST go through full 3-phase analysis
    - Do NOT skip phases based on "trivially safe" judgments
    - Complex bugs hide in simple-looking code
  </optimization_strategy>

  <instructions>
    1. **Initialize**: Read <ref id="queue"/> to get `item_ids` and `context_file` path. Read <ref id="context"/> to get item data (keyed by ID). For each ID in `item_ids`, look up the item data in context. Create `results = []`.

    2. **Group Items by Component**:
       - Group items by `code_scope.locations[0].file` (primary file)
       - Items from same file can share context
       - This enables batch skill invocation

    3. **Process Each Item** (prepare for batch):
       a. **Check Pre-resolved Code**: If `item.code_scope.resolution_status == "resolved"` and `item.code_scope.locations` is not empty:
          - Use pre-resolved data from Phase 02c
          - Primary location is first item with `role == "primary"` in locations array
          - Related locations (callers, callees, state management) are available for context
          - Use `item.code_excerpt` which contains all relevant code sections
       
       b. **Resolve Code (if needed)**: If not pre-resolved, use `mcp__tree_sitter__get_symbols` or `mcp__tree_sitter__run_query` to find file/line numbers from `item.checklist_item.graph_element_under_test`. Use `mcp__filesystem__read_text_file` to extract relevant lines as `code_excerpt`.

       c. **Expand Context for State Analysis**:
          - Use `mcp__filesystem__search_files` to find related state management code
          - Look for cache structures, concurrent access patterns
          - Include caller/callee context to understand state flow
          
       d. **Include Location**: Output MUST include:
          - `code_scope`: {locations: [{file, symbol, line_range, role}], resolution_status}
          - `code_snippet`: actual code excerpt (primary location or combined from Phase 02c)
          - `state_context`: related state management code (cache, locks, etc.)

       e. **Skip Check**: If `code_scope.resolution_status` is `not_found`/`specification_only`/`out_of_scope`, OR all locations are external (`vendor/`, submodules), OR component mismatch:
          Create result with `final_classification = "out-of-scope"`, append to `results`, continue to next item.

       f. **Collect for Batch Processing**: Add item to appropriate group for batch skill invocation.

    4. **Batch Skill Invocation with Adversarial Context**:
       a. **For Each File Group** (items from same file):
          - Call `/formal-audit-adversarial` skill with ALL items from this file
          - Pass combined context: code_excerpts, state_context, properties, check_ids
          - **Emphasize adversarial mindset** in skill invocation
          - Request detailed analysis, not summaries
       
       b. **Quality Check**:
          - Verify skill output includes concrete attack scenarios
          - Ensure all phases were executed (no early exits)
          - Check that guards were challenged, not just identified

    5. **Merge Results**: For each item, map to the minimal schema:
       - id = checklist/check_id
       - classification (allowed set)
       - code_path (primary location file::symbol::Lstart-end)
       - proof_trace (succinct rationale or root cause/proof)
       - attack_scenario (only for vulns/potential; else "")
       - checklist_id (duplicate of id for downstream compatibility)

    6. **Write Output**: After ALL items processed, write a JSON object with `metadata` and `audit_items` to <ref id="results"/>.

    7. **Confirm**: On stdout, print a one-line summary (<=5 lines total) and `Output File: {{OUTPUT_FILE}}`.

    8. **Turn budget**: Complete the batch in a single assistant turn if possible (the orchestrator may cap max_turns_per_batch).
  </instructions>

  <data_sources>
    - **Checklist Item**: `item.checklist_item`
    - **Subgraph**: `item.subgraph` (pre-extracted, included in item)
    - **Tree-sitter MCP**: MUST use `mcp__tree_sitter__get_symbols`/`run_query` for code resolution
    - **Filesystem MCP**: Use `mcp__filesystem__read_text_file` with `head`/`tail` for efficient partial reads
    - **Search MCP**: Use `mcp__filesystem__search_files` to find state management code
  </data_sources>

</task>

<output>
  <format>
    - Write a single JSON object with two keys:
      - "metadata": keep the existing metadata structure (phase, worker_id, batch_index, item_count, timestamp, processed_ids, etc.) unchanged.
      - "audit_items": an array of result rows. Each row MUST contain ONLY the following keys, nothing else:
        1) "id"                -> same as checklist_id / check_id string
        2) "classification"    -> one of: vulnerability | potential-vulnerability | not-a-vulnerability | informational | out-of-scope
        3) "code_path"         -> string like "path/to/file.go::FuncName::L22-33" (primary location)
        4) "proof_trace"       -> 
           - if classification is vulnerability or potential-vulnerability: concise root cause statement + short proof / why the guard fails (1–3 sentences)
           - otherwise: concise rationale why it is safe or out-of-scope (1–3 sentences)
        5) "attack_scenario"   -> 
           - if vulnerability/potential-vulnerability: one concrete exploit path (1–2 sentences)
           - otherwise: empty string ""
        6) "checklist_id"      -> the checklist/check_id string
    - Do NOT emit any other fields (no severity, confidence, bug_bounty_eligible, phases, state_context, summaries, recommendations, counts, or headers).
    - Preserve JSON ordering above for readability.
  </format>
  <stdout>Max 5 lines: e.g., "items=5 vuln=1 out_of_scope=2 safe=2".</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>

<quality_gates>
  **Before writing output, verify:**
  
  1. **Field whitelist**: Every audit_items element has exactly the 6 allowed keys (id, classification, code_path, proof_trace, attack_scenario, checklist_id). No extras.
  2. **Non-empty rationale**: proof_trace non-empty (<= 3 sentences). attack_scenario non-empty only for vulnerability/potential-vulnerability; otherwise exactly "".
  3. **Code path present**: code_path includes file, symbol (if available), and line range e.g., `beacon-chain/core/peerdas/reconstruction.go::ReconstructDataColumnSidecars::L31-122`.
  4. **Classification sanity**: use allowed set only.
  5. **Metadata preserved**: metadata object is still included and unchanged except for fields you legitimately update (e.g., timestamp, processed_ids).
</quality_gates>

<anti_patterns>
  **AVOID these common mistakes:**
  
  ❌ "This code has validation, so it's safe" → ✅ "Is validation sufficient for ALL scenarios?"
  ❌ "No counterexample found, mark as safe" → ✅ "Why couldn't I find one? Is it complex?"
  ❌ "Code looks simple, skip detailed analysis" → ✅ "Complex bugs hide in simple code"
  ❌ "Early exit to save tokens" → ✅ "Full analysis to find real bugs"
</anti_patterns>
