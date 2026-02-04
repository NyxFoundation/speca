
---
Description: [WORKER] Invoke the formal-audit skill for a batch of items.
Usage: `/03_auditmap_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]`
Example: `/03_auditmap_worker WORKER_ID=0 QUEUE_FILE=outputs/03_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=5 OUTPUT_FILE=outputs/03_AUDITMAP_PARTIAL_W0_1700000000_1.json`
Language: English only.
Execution hint: This worker prompt is invoked by the phase-03 async orchestrator.
---
**Use Serena MCP tools (find_symbol, insert_after_symbol, etc.) for efficient code navigation and editing.**

<task>
  <goal>Run a three-stage formal audit for each item in the batch using skills.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <instructions>
    1. Read <ref id="queue"/> and select the first BATCH_SIZE unprocessed items.
    2. For each item, resolve the code scope using Tree-sitter MCP tools. Based on `item.checklist_item.graph_element_under_test`, use `get_symbols` or `run_query` to find the relevant file path and line numbers. Extract this code as `code_excerpt`.
    3. Apply Early Exit Conditions. If the code scope cannot be resolved or is out of scope, skip to step 5.
    4. If a `code_excerpt` is found, run these skills in order:
       a) /formal-audit-phase1 (include code_excerpt)
       b) /formal-audit-phase2 (include phase1 output)
       c) /formal-audit-phase3 (include phase1+phase2 outputs)
    5. Merge outputs into a single audit result object per item.
    6. Write a JSON array of audit result objects to <ref id="results"/>.
  </instructions>

  <data_sources>
    - **Checklist Item**: `item.checklist_item` (already resolved)
    - **Property File**: `outputs/01e_PROP_PARTIAL_*.json` (for property assertion)
    - **Subgraph**: `item.subgraph` (pre-extracted relevant subgraph, included in the item)
    - **Tree-sitter MCP**: Use `get_symbols` and `run_query` to actively find code.
  </data_sources>

  <early_exit_conditions>
    Skip all phases and set `final_classification = "out-of-scope"` if:
    - `code_scope.file` is `N/A`, `SPECIFICATION-ONLY`, or missing
    - Code resolves to external dependency (`vendor/`, submodules)
    - Component mismatch (EL vs CL)
  </early_exit_conditions>
</task>

<output>
  <format>JSON array</format>
  <stdout>Max 8 lines: batch size, items processed, short status.</stdout>
</output>
