
---
Description: [WORKER] Pre-resolve code locations for checklist items
Usage: `/02c_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]`
Language: English only.
---

<task>
  <goal>For each checklist item in the batch, find the relevant code locations in the target repository and extract code excerpts.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    1. Process ALL items in the batch — do not skip or truncate
    2. Write output JSON even if some items fail resolution
    3. Handle errors per item gracefully and continue
  </critical_requirements>

  <instructions>
    ## Step 1: Setup

    Read `outputs/02c_TARGET_INFO.json`. It contains:
    - `target_repo`: repository identifier (e.g. "OffchainLabs/prysm")
    - `target_layer` *(optional)*: the functional layer this target belongs to (e.g. "consensus", "execution", "l2-node", "validator-runtime")
    - `out_of_scope_spec_layers` *(optional)*: list of spec layer strings that are out of scope for this target (e.g. `["execution"]`)

    Register the cloned repository at `target_workspace/` with Tree-sitter MCP.

    ## Step 2: Layer Scope Check (per item, only if TARGET_INFO has `out_of_scope_spec_layers`)

    If `out_of_scope_spec_layers` is present and non-empty, infer the spec layer for each item from its `notes` field (look for layer keywords or spec identifiers). If the inferred layer matches any entry in `out_of_scope_spec_layers` → mark as `out_of_scope` and skip to next item.

    When `out_of_scope_spec_layers` is absent or empty, skip this check entirely and treat all items as in-scope.

    ## Step 3: Code Resolution (per in-scope item)

    **Primary — Tree-sitter MCP call graph:**
    Use Tree-sitter MCP to identify entry point functions matching `reachability.entry_points`, then traverse the call graph (depth ≤ 3) to find functions whose names or logic match keywords extracted from `test_procedure`. Extract file path, symbol name, and line range for the top matches.

    **Fallback — Glob + Grep:**
    If MCP fails or returns no results, use the standard Glob and Grep tools to search `target_workspace/` directly. Extract keywords (identifiers, constants, domain terms) from `test_procedure`, then search for matching function/type definitions. Use `reachability.entry_points` as a hint to narrow the search directory (e.g. an entry point named "P2P" likely maps to directories like `p2p/`, `sync/`, `network/`; "Transaction" to `txpool/`, `core/`; infer from the codebase structure if uncertain).

    Read the matched file sections with the Read tool to extract code excerpts (max 50 lines per location).

    If both MCP and Grep find nothing → mark as `not_found`.

  </instructions>

  <output>
    <format>JSON object with "checklist_with_code" array</format>
    <schema>
      {
        "checklist_with_code": [
          {
            // ALL original fields from the input item must be preserved as-is

            "code_scope": {
              "locations": [           // empty list if out_of_scope or not_found
                {
                  "file": "relative/path/from/workspace/root.go",
                  "symbol": "FunctionOrTypeName",
                  "line_range": { "start": 42, "end": 78 },
                  "role": "primary" | "caller" | "callee" | "related"
                }
              ],
              "resolution_status": "resolved" | "out_of_scope" | "not_found" | "error",
              "resolution_error": "",   // empty string unless status is "error"
              "resolution_method": "mcp_callgraph" | "mcp_simple" | "grep_fallback"  // only when resolved
            },
            "code_excerpt": "// PRIMARY: path/to/file.go:FunctionName (lines 42-78)\n..."
          }
        ]
      }
    </schema>
    <stdout>Max 10 lines: processed count and per-status breakdown.</stdout>
    <final_line>Output File: {{OUTPUT_FILE}}</final_line>
  </output>
</task>
