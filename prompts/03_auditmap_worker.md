
---
Description: [WORKER] Invoke the formal-audit skill for a batch of items using MCP tools.
Usage: `/03_auditmap_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]`
Example: `/03_auditmap_worker WORKER_ID=0 QUEUE_FILE=outputs/03_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=5 OUTPUT_FILE=outputs/03_AUDITMAP_PARTIAL_W0_1700000000_1.json`
Language: English only.
Execution hint: This worker prompt is invoked by the phase-03 async orchestrator with MCP tools enabled.
---

<task>
  <goal>For each item in the batch, use MCP tools to resolve the code scope and then invoke the /formal-audit skill to perform a three-stage formal audit.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    **YOU MUST COMPLETE ALL OF THE FOLLOWING:**
    1. Process ALL items in the batch (up to BATCH_SIZE)
    2. After processing ALL items, write a JSON file to <ref id="results"/>
    3. The JSON file MUST be written even if some items are skipped

    **FAILURE TO WRITE THE JSON FILE IS A CRITICAL ERROR.**
  </critical_requirements>

  <instructions>
    1. **Initialize**: Read <ref id="queue"/> and select the first BATCH_SIZE unprocessed items. Create an empty array `results = []`.

    2. **Process Each Item**: For each item in the batch, perform steps 2a-2e:
    
       2a. **Resolve Code Scope**: Use Tree-sitter MCP tools (`mcp__tree_sitter__get_symbols` or `mcp__tree_sitter__run_query`) to find the relevant file path and line numbers based on `item.checklist_item.graph_element_under_test`. Extract this code as `code_excerpt`.
       
       2b. **Check Skip Conditions**: If any of the following conditions are met:
           - `code_scope.file` is `N/A`, `SPECIFICATION-ONLY`, or missing
           - Code resolves to external dependency (`vendor/`, submodules)
           - Component mismatch (EL vs CL)
           
           Then: Create a result object with `final_classification = "out-of-scope"`, append it to `results`, and **proceed to the next item** (do NOT exit).
       
       2c. **Run Formal Audit Skills**: If a valid `code_excerpt` is found, run these skills in order:
           - /formal-audit-phase1 (include code_excerpt)
           - /formal-audit-phase2 (include phase1 output)
           - /formal-audit-phase3 (include phase1+phase2 outputs)
       
       2d. **Merge Outputs**: Merge skill outputs into a single audit result object for this item.
       
       2e. **Append and Continue**: Append the result object to `results`. **Proceed to the next item.**

    3. **Write Output File**: After ALL items have been processed, write the `results` array to <ref id="results"/>.
       - This step is **MANDATORY**.
       - Even if all items were skipped, write the array containing the skip classifications.

    4. **Confirm Completion**: Print a summary and end with: `Output File: {{OUTPUT_FILE}}`
  </instructions>

  <data_sources>
    - **Checklist Item**: `item.checklist_item` (already resolved)
    - **Property File**: `outputs/01e_PROP_PARTIAL_*.json` (for property assertion)
    - **Subgraph**: `item.subgraph` (pre-extracted relevant subgraph, included in the item)
    - **Tree-sitter MCP**: You **MUST** use `mcp__tree_sitter__get_symbols` and `mcp__tree_sitter__run_query` to find code. Direct file access for code resolution is **NOT PERMITTED**.
  </data_sources>
</task>

<output>
  <format>JSON array</format>
  <stdout>Max 8 lines: batch size, items processed, short status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>
