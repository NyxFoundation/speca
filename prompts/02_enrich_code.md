---
Description: [OPTIONAL] Enrich checklist items with pre-resolved code locations
Usage: `/02_enrich_code INPUT_FILE=... OUTPUT_FILE=...`
Example: `/02_enrich_code INPUT_FILE=outputs/02_CHECKLIST_ENRICHED.json OUTPUT_FILE=outputs/02_CHECKLIST_WITH_CODE.json`
Language: English only.
Execution hint: This is an optional optimization step between Phase 02 and Phase 03.
---

<task>
  <goal>Pre-resolve code locations for checklist items to reduce MCP overhead in Phase 03.</goal>
  <input type="file" id="input">{{INPUT_FILE}}</input>
  <output type="file" id="output">{{OUTPUT_FILE}}</output>

  <rationale>
    By resolving code locations once before Phase 03:
    - **Reduce redundant MCP calls**: Each location resolved once, not per-worker
    - **Enable better caching**: Tree-sitter results cached across items
    - **Improve Phase 03 speed**: Workers start immediately without code resolution
  </rationale>

  <instructions>
    1. **Load Input**: Read <ref id="input"/> containing checklist items with `resolution_status="pending"`.

    2. **Batch Resolution**: For items where `code_scope.resolution_status == "pending"`:
       a. Extract `graph_element_under_test` (e.g., "beacon_chain.go:ProcessBlock")
       b. Use `mcp__tree_sitter__get_symbols` to find the symbol
       c. If found:
          - Set `code_scope.file`, `code_scope.function`, `code_scope.line_range`
          - Set `code_scope.resolution_status = "resolved"`
          - Use `mcp__filesystem__read_text_file` with `head`/`tail` to extract `code_excerpt`
       d. If not found:
          - Set `code_scope.resolution_status = "not_found"` or `"ambiguous"`
          - Set `code_scope.resolution_error` with details

    3. **Optimize MCP Usage**:
       - **Cache symbols**: Call `mcp__tree_sitter__analyze_project` once at start
       - **Batch by file**: Group items by file to minimize tree-sitter calls
       - **Skip duplicates**: If multiple items reference same function, resolve once

    4. **Write Output**: Save all items (with enriched `code_scope` and `code_excerpt`) to <ref id="output"/>.

    5. **Report**: Print summary:
       - Total items processed
       - Successfully resolved
       - Not found / ambiguous
       - Estimated MCP calls saved in Phase 03
  </instructions>

  <output_format>
    JSON object with key `checklist` containing array of enriched ChecklistItem objects.
    Each item should have:
    - `code_scope.file`: file path (or empty if not found)
    - `code_scope.function`: function name
    - `code_scope.line_range`: e.g., "100-150"
    - `code_scope.resolution_status`: "resolved" | "not_found" | "ambiguous" | "pending"
    - `code_excerpt`: actual code text (if resolved)
  </output_format>
</task>

<optimization_notes>
  This is an **optional** step. If skipped, Phase 03 workers will resolve code on-demand.
  
  Expected savings:
  - **Without this step**: ~2-3 MCP calls per item × 500 items = 1000-1500 calls
  - **With this step**: ~200-300 unique symbols = 200-300 calls
  - **Net savings**: 70-80% reduction in code resolution overhead
</optimization_notes>
