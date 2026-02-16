
---
Description: [WORKER] Invoke the unified formal-audit skill for a batch of items using MCP tools.
Usage: `/03_auditmap_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]`
Example: `/03_auditmap_worker WORKER_ID=0 QUEUE_FILE=outputs/03_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=5 OUTPUT_FILE=outputs/03_PARTIAL_W0_1700000000_1.json`
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

  <optimization_strategy>
    **CRITICAL PERFORMANCE REQUIREMENTS**:
    
    **1. Batch Skill Invocation** (minimize invocation count):
    - **Target**: 1-5 skill calls for 15-item batch (not 15 individual calls)
    - **Method**: Group items by file/component, invoke skill once per group
    - **Benefit**: Reduces skill invocations from O(n) to O(k) where k=unique files (typically 3-5x reduction)
    
    **2. Cache Optimization** (maximize cache hits):
    - **Group by file**: Items from same file share context (maximize cache hits)
    - **Reuse context**: Keep common context (skill definitions, schema) in same conversation
    - **Minimal payload**: Pass only essential context per skill call
    - **Prompt structure**: Maintain consistent prompt structure for automatic caching
    
    **3. Expected Performance**:
    - 15 items → 3-5 skill calls (if well-grouped by file)
    - Cache hit rate: 70-90% through batching
    - Token reduction: 40-60% vs individual processing
  </optimization_strategy>

  <instructions>
    1. **Initialize**: Read <ref id="queue"/>, select first BATCH_SIZE items. Create `results = []`.

    2. **Group Items by Component**:
       - Group items by `code_scope.locations[0].file` (primary file)
       - Items from same file can share context and be analyzed together
       - This enables batch skill invocation (see step 4)

    3. **Process Each Item** (prepare for batch):
       a. **Check Pre-resolved Code**: If `item.code_scope.resolution_status == "resolved"` and `item.code_scope.locations` is not empty:
          - Use pre-resolved data from Phase 02c
          - Primary location is first item with `role == "primary"` in locations array
          - Related locations (callers, callees) are available for context
          - Use `item.code_excerpt` which contains all relevant code sections
       
       b. **Resolve Code (if needed)**: If not pre-resolved, use `mcp__tree_sitter__get_symbols` or `mcp__tree_sitter__run_query` to find file/line numbers from `item.checklist_item.graph_element_under_test`. Use `mcp__filesystem__read_text_file` to extract relevant lines as `code_excerpt`.

       c. **Include Location**: Output MUST include:
          - `code_scope`: {locations: [{file, symbol, line_range, role}], resolution_status}
          - `code_snippet`: actual code excerpt (primary location or combined from Phase 02c)

       d. **Skip Check**: If `code_scope.resolution_status` is `not_found`/`specification_only`/`out_of_scope`, OR all locations are external (`vendor/`, submodules), OR component mismatch:
          Create result with `final_classification = "out-of-scope"`, append to `results`, continue to next item.

       e. **Collect for Batch Processing**: Add item to appropriate group for batch skill invocation.

    4. **Batch Skill Invocation** (preferred):
       a. **For Each File Group** (items from same file):
          - **Preferred**: Call `/formal-audit-unified` skill ONCE with ALL items from this file
          - Pass combined context: all code_excerpts, all properties, all check_ids
          - Skill processes all items in single context (maximum cache reuse)
          - Reduces skill calls from n items to k files (typically 5-10x reduction)
       
       b. **Fallback** (if skill doesn't support batch):
          - Process items individually within same conversation
          - Still benefit from cache hits for repeated context
          - But avoid context fork overhead between items

    5. **Merge Results**: Merge skill output into result objects, append all to `results`.

    6. **Write Output**: After ALL items processed, write `results` array to <ref id="results"/>.

    7. **Confirm**: Print summary including:
       - Total items processed
       - Number of skill invocations (should be << total items)
       - Items per skill call (average)
       End with: `Output File: {{OUTPUT_FILE}}`
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
