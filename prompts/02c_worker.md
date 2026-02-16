
---
Description: [WORKER] Pre-resolve code locations for checklist items before Phase 03
Usage: `/02c_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]`
Example: `/02c_worker WORKER_ID=0 QUEUE_FILE=outputs/02c_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=100 OUTPUT_FILE=outputs/02c_CODE_RESOLVED_PARTIAL_W0_1700000000_1.json`
Language: English only.
Execution hint: This worker prompt is invoked by the phase-02c orchestrator with Tree-sitter and Filesystem MCP tools enabled.
---

<task>
  <goal>For each checklist item in the batch, resolve code locations using MCP tools and populate code_scope and code_excerpt fields.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    1. Process ALL items in the batch
    2. Use Tree-sitter MCP tools (mcp__tree_sitter__*) for code resolution
    3. Use Filesystem MCP tools (mcp__filesystem__*) for reading code excerpts
    4. Write JSON file to <ref id="results"/> after processing ALL items
    5. File MUST be written even if some items fail resolution
  </critical_requirements>

  <instructions>
    1. **Initialize**: Read <ref id="queue"/>, select first BATCH_SIZE items. Create `results = []`.

    2. **Batch Symbol Collection**:
       - Extract ALL `graph_element_under_test` values from all items in batch
       - Create a deduplicated list of symbols to search
       - Group by expected file/component for efficient searching
       - This reduces MCP calls from O(n*m) to O(n) where n=unique symbols, m=operations per symbol

    3. **Batch Code Resolution** (prefer batch processing):
       a. **Option A - Project-wide Analysis** (recommended, most efficient):
          - Use `mcp__tree_sitter__analyze_project` ONCE for the entire target workspace
          - This creates a symbol cache that can be queried in-memory
          - Then iterate through items using cached results (no additional MCP calls)
       
       b. **Option B - Batch Symbol Search** (alternative):
          - Use `mcp__tree_sitter__run_query` with a combined query for all symbols at once
          - Example: `(function_definition name: (identifier) @name (#match? @name "^(Symbol1|Symbol2|Symbol3)$"))`
          - This reduces multiple `find_symbol` calls to a single batch query

    4. **Process Each Item** (using cached/batch results):
       a. **Extract Element Info**: Get `graph_element_under_test` from checklist item. If missing or empty, mark as `resolution_status: "no_element"`, append to results, continue.

       b. **Resolve Primary Code Location** (from cached/batch results):
          - Look up the graph element in cached results from step 3
          - If using Option A (analyze_project): query the cached symbol table
          - If using Option B (batch query): extract from batch query results
          - Extract: file path, symbol name (in name_path format), line range (start/end)
          - This becomes the **primary** location (role: "primary")
          - **NO additional MCP calls per item**

       c. **Find Related Code Locations** (batch where possible):
          - **Callers**: Collect all primary symbols first, then batch call `find_referencing_symbols` for all at once
          - **Callees**: Extract from primary symbol body (already cached) using regex or tree-sitter parse
          - **Related**: Extract from checklist item description, lookup in cached results
          - For each related location, extract: file, symbol, line_range
          - Limit to top 10 most relevant locations to avoid excessive data

       d. **Extract Code Excerpts** (from cached results):
          - PRIMARY location: extract from cached symbol bodies (already loaded in step 3)
          - RELATED locations: extract from cached results where available
          - Only use `mcp__filesystem__read_text_file` if symbol body not in cache (rare)
          - Store combined excerpts in `code_excerpt` field with clear markers:
            ```
            // PRIMARY: path/to/file.go:FunctionName (lines 10-50)
            [code here]
            
            // CALLER: path/to/caller.go:CallerFunc (lines 100-120)
            [code here]
            ```

       e. **Populate Result**:
          - Create result with:
            - `check_id`: from original item
            - `code_scope`: {
                locations: [
                  {file, symbol, line_range: {start, end}, role: "primary"},
                  {file, symbol, line_range: {start, end}, role: "caller"},
                  ...
                ],
                resolution_status
              }
            - `code_excerpt`: combined code text with clear section markers (if found)
          - Set `resolution_status`:
            - `"resolved"`: Successfully found primary and related code
            - `"not_found"`: Element not found in target codebase
            - `"specification_only"`: Element is specification-level, no code exists
            - `"error"`: Error during resolution

       f. **Append & Continue**: Append result to `results`, continue to next item.

    3. **Write Output**: After ALL items processed, write `results` array to <ref id="results"/>.

    4. **Confirm**: Print summary with counts:
       - Total items processed
       - Successfully resolved
       - Not found
       - Specification-only
       - Errors
       End with: `Output File: {{OUTPUT_FILE}}`
  </instructions>

  <search_strategies>
    For different graph element types, use appropriate search methods:
    
    **Functions/Methods**:
    - Use `mcp__tree_sitter__find_symbol` with name path pattern
    - Example: `FunctionName` or `ClassName/methodName`
    
    **Classes/Interfaces**:
    - Use `mcp__tree_sitter__find_symbol` with class name
    - Example: `ClassName`
    
    **Variables/Constants**:
    - Use `mcp__tree_sitter__run_query` with Tree-sitter query
    - Example query: `(variable_declaration name: (identifier) @name)`
    
    **Complex patterns**:
    - Use `mcp__tree_sitter__run_query` with custom queries
    - Reference element description for context
  </search_strategies>

  <data_sources>
    - **Checklist Items**: Input queue from Phase 02
    - **Target Codebase**: `target_workspace/` directory (checked out by workflow)
    - **Tree-sitter MCP**: For symbolic code navigation
    - **Filesystem MCP**: For reading file contents
  </data_sources>

  <scope_filtering>
    Apply scope filtering based on AUDIT_SCOPE environment variable:
    - `"cl"`: Consensus Layer only
    - `"el"`: Execution Layer only
    - `"both"`: Both layers
    - `"auto"`: Infer from target repository
    
    Mark items outside scope as `resolution_status: "out_of_scope"`.
  </scope_filtering>

  <performance_notes>
    **MCP Call Optimization (CRITICAL)**:
    - **Target**: 1-10 MCP calls total for 100-item batch (not 300-400 calls per item)
    - **Method**: Use `mcp__tree_sitter__analyze_project` ONCE, then query cached results
    - **Fallback**: Use batch queries with combined symbol patterns
    - **Avoid**: Individual `find_symbol` calls per item (too expensive)
    
    **Batching**:
    - Process items in batches of up to 100 for efficiency (max_batch_size=100)
    - Group items by file/component before making MCP calls
    - Deduplicate symbol lookups across items
    
    **Resource Limits**:
    - Limit total code excerpts to 500 lines max across ALL locations to avoid token bloat
    - Limit related locations to top 10 most relevant (prioritize direct callers/callees)
    - For large symbols (>100 lines), consider truncating excerpts with "... [truncated] ..."
  </performance_notes>
</task>

<output>
  <format>JSON array of enriched checklist items</format>
  <schema>
    {
      "check_id": "string",
      "code_scope": {
        "locations": [
          {
            "file": "string",
            "symbol": "string (name_path format, e.g., 'ClassName/methodName')",
            "line_range": {"start": int, "end": int},
            "role": "primary|caller|callee|related"
          }
        ],
        "resolution_status": "resolved|not_found|specification_only|out_of_scope|error",
        "resolution_error": "string (optional)"
      },
      "code_excerpt": "string (optional, combined excerpts with section markers)"
    }
  </schema>
  <stdout>Max 10 lines: batch size, resolution stats, status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>
