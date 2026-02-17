
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
    1. **Initialize**: Read <ref id="queue"/>, select first BATCH_SIZE items. Create `results = []`.

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

    5. **Merge Results**: Merge skill output into result objects, append all to `results`.

    6. **Write Output**: After ALL items processed, write `results` array to <ref id="results"/>.

    7. **Confirm**: Print summary including:
       - Total items processed
       - Number of vulnerabilities found (bug_bounty_eligible: true)
       - Number of skill invocations
       - Average analysis depth (phases executed per item)
       End with: `Output File: {{OUTPUT_FILE}}`
  </instructions>

  <data_sources>
    - **Checklist Item**: `item.checklist_item`
    - **Subgraph**: `item.subgraph` (pre-extracted, included in item)
    - **Tree-sitter MCP**: MUST use `mcp__tree_sitter__get_symbols`/`run_query` for code resolution
    - **Filesystem MCP**: Use `mcp__filesystem__read_text_file` with `head`/`tail` for efficient partial reads
    - **Search MCP**: Use `mcp__filesystem__search_files` to find state management code
  </data_sources>

  <quality_gates>
    **Before writing output, verify:**
    
    1. **No Premature Dismissals**:
       - Items marked "not-a-vulnerability" MUST have concrete justification
       - "Guards exist" is NOT sufficient justification alone
       - Must explain why guards are SUFFICIENT for all attack scenarios
    
    2. **Concrete Attack Scenarios**:
       - Items marked "vulnerability" MUST have concrete exploit description
       - Include specific inputs, timing, or state combinations
    
    3. **Full Analysis**:
       - Every item MUST have all phase outputs (phase1, phase2, phase2_5, phase3, phase3_5)
       - No empty or missing phase results
    
    4. **Conservative Bias**:
       - When uncertain, lean toward reporting (bug_bounty_eligible: true)
       - Document uncertainty in reasoning
  </quality_gates>
</task>

<output>
  <format>JSON array</format>
  <stdout>Max 10 lines: batch size, items processed, vulnerabilities found, status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>

<anti_patterns>
  **AVOID these common mistakes:**
  
  ❌ "This code has validation, so it's safe" → ✅ "Is validation sufficient for ALL scenarios?"
  ❌ "No counterexample found, mark as safe" → ✅ "Why couldn't I find one? Is it complex?"
  ❌ "Code looks simple, skip detailed analysis" → ✅ "Complex bugs hide in simple code"
  ❌ "Early exit to save tokens" → ✅ "Full analysis to find real bugs"
</anti_patterns>
