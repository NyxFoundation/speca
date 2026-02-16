
---
Description: [WORKER] Invoke the unified formal-audit skill for a batch of items using MCP tools.
Usage: `/03_auditmap_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]`
Example: `/03_auditmap_worker WORKER_ID=0 QUEUE_FILE=outputs/03_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=5 OUTPUT_FILE=outputs/03_AUDITMAP_PARTIAL_W0_1700000000_1.json`
Language: English only.
Execution hint: This worker prompt is invoked by the phase-03 async orchestrator with MCP tools enabled.
---

<task>
  <goal>For each item in the batch, resolve code scope and invoke /formal-audit-unified skill.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    1. Process ALL items in the batch
    2. Write JSON file to <ref id="results"/> after processing ALL items
    3. File MUST be written even if some items are skipped
  </critical_requirements>

  <cache_optimization>
    To minimize token consumption, follow these caching guidelines:
    - **Reuse context**: Keep common context (skill definitions, checklist schema) in the same conversation
    - **Batch similar items**: Process items from the same file/component together to maximize cache hits
    - **Minimal context**: Only include necessary information in each skill invocation
    - **Leverage prompt caching**: Structure prompts to maximize Claude API's automatic prompt caching
  </cache_optimization>

  <instructions>
    1. **Initialize**: Read <ref id="queue"/>, select first BATCH_SIZE items. Create `results = []`.

    2. **Process Each Item**:
       a. **Check Pre-resolved Code**: If `item.code_scope.resolution_status == "resolved"` and `item.code_excerpt` exists, skip code resolution and use pre-resolved data.
       
       b. **Resolve Code (if needed)**: Otherwise, use `mcp__tree_sitter__get_symbols` or `mcp__tree_sitter__run_query` to find file/line numbers from `item.checklist_item.graph_element_under_test`. Use `mcp__filesystem__read_text_file` with `head`/`tail` to extract relevant lines as `code_excerpt`.

       c. **Include Location**: Output MUST include:
          - `code_scope`: {file, function, line_range}
          - `code_snippet`: actual code excerpt

       d. **Skip Check**: If `code_scope.file` is `N/A`/`SPECIFICATION-ONLY`/missing, OR code is external (`vendor/`, submodules), OR component mismatch:
          Create result with `final_classification = "out-of-scope"`, append to `results`, continue to next item.

       e. **Run Audit**: If valid `code_excerpt` found, call `/formal-audit-unified` skill (single call, not phase1/2/3 separately).
          - **Cache-friendly invocation**: Pass only essential context to the skill (code_excerpt, property, check_id)
          - **Avoid redundancy**: Do not repeat information already in the skill's context

       f. **Merge & Continue**: Merge skill output into result object, append to `results`, proceed to next item.

    3. **Write Output**: After ALL items processed, write `results` array to <ref id="results"/>.

    4. **Confirm**: Print summary, end with: `Output File: {{OUTPUT_FILE}}`
  </instructions>

  <data_sources>
    - **Checklist Item**: `item.checklist_item`
    - **Subgraph**: `item.subgraph` (pre-extracted, included in item)
    - **Tree-sitter MCP**: MUST use `mcp__tree_sitter__get_symbols`/`run_query` for code resolution
    - **Filesystem MCP**: Use `mcp__filesystem__read_text_file` with `head`/`tail` for efficient partial reads
  </data_sources>
</task>

<output>
  <format>JSON array</format>
  <stdout>Max 8 lines: batch size, items processed, status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>
