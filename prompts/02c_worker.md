
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

    2. **Process Each Item**:
       a. **Extract Element Info**: Get `graph_element_under_test` from checklist item. If missing or empty, mark as `resolution_status: "no_element"`, append to results, continue.

       b. **Resolve Code Location**:
          - Use `mcp__tree_sitter__find_symbol` or `mcp__tree_sitter__run_query` to search for the graph element
          - Search in `target_workspace/` directory (target repository)
          - Try multiple search strategies:
            1. Direct symbol name search
            2. Substring matching if exact match fails
            3. Pattern-based search using Tree-sitter queries
          - Extract file path, function/class name, and line range

       c. **Extract Code Excerpt**:
          - Once location is found, use `mcp__tree_sitter__get_symbols` with `include_body=true` to get full symbol body
          - OR use `mcp__filesystem__read_text_file` with appropriate line range
          - Store in `code_excerpt` field (max 500 lines for performance)

       d. **Populate Result**:
          - Create result with:
            - `check_id`: from original item
            - `code_scope`: {file, function, line_range, resolution_status}
            - `code_excerpt`: actual code text (if found)
          - Set `resolution_status`:
            - `"resolved"`: Successfully found and extracted code
            - `"not_found"`: Element not found in target codebase
            - `"specification_only"`: Element is specification-level, no code exists
            - `"error"`: Error during resolution

       e. **Append & Continue**: Append result to `results`, continue to next item.

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
    - Process items in batches of up to 1000 for efficiency
    - Use Tree-sitter caching by grouping items from same files
    - Limit code excerpts to 500 lines max to avoid token bloat
    - Use `substring_matching=true` in find_symbol for fuzzy matches
  </performance_notes>
</task>

<output>
  <format>JSON array of enriched checklist items</format>
  <schema>
    {
      "check_id": "string",
      "code_scope": {
        "file": "string",
        "function": "string",
        "line_range": {"start": int, "end": int},
        "resolution_status": "resolved|not_found|specification_only|out_of_scope|error"
      },
      "code_excerpt": "string (optional, only if resolved)"
    }
  </schema>
  <stdout>Max 10 lines: batch size, resolution stats, status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>
