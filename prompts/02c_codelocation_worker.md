
---
Description: [WORKER] Pre-resolve code locations for properties (OPTIMIZED: metadata only, no code excerpts)
Usage: `/02c_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]`
Language: English only.
---

<task>
  <goal>For each property in the batch, find the relevant code locations in the target repository. Return ONLY file paths, function names, and line ranges — do NOT extract code excerpts.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <input type="file" id="context">{{CONTEXT_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    1. Process ALL items in the batch — do not skip or truncate
    2. Write output JSON even if some items fail resolution
    3. Handle errors per item gracefully and continue
    4. **DO NOT extract or include code excerpts** — only metadata (file path, symbol name, line range)
  </critical_requirements>

  <instructions>
    ## Step 1: Setup

    Read <ref id="queue"/> to get `item_ids` and `context_file` path. Read <ref id="context"/> to get item data (keyed by ID). For each ID in `item_ids`, look up the item data in context.

    Read `outputs/TARGET_INFO.json`. It contains:
    - `target_repo`: repository identifier (e.g. "OffchainLabs/prysm")
    - `target_layer` *(optional)*: the functional layer this target belongs to (e.g. "consensus", "execution", "l2-node", "validator-runtime")
    - `out_of_scope_spec_layers` *(optional)*: list of spec layer strings that are out of scope for this target (e.g. `["execution"]`)

    Register the cloned repository at `target_workspace/` with Tree-sitter MCP.

    Read `outputs/01b_SUBGRAPH_INDEX.json` for spec-level context. This index maps
    specification titles to their subgraphs (name + mermaid file path). For each
    property, match keywords from `text`/`assertion` against subgraph names to identify
    the relevant spec. Read the corresponding `.mmd` mermaid file to extract
    spec-level function names, state transitions, and invariants — use these as
    additional search keywords when resolving code locations.

    ## Step 2: Layer Scope Check (per item)

    **When `out_of_scope_spec_layers` is present** in TARGET_INFO: infer the spec layer for each item from its `covers` string and property `text`. If the inferred layer matches any entry in `out_of_scope_spec_layers` → mark as `out_of_scope` and skip to next item.

    **Heuristic fallback** (when `out_of_scope_spec_layers` is absent or empty): use the repo orientation from Step 2.5 to infer scope. If the property clearly belongs to a domain with no matching top-level package in the target (e.g. the property references EVM opcodes/gas scheduling but the repo has no `core/vm/`, `evm/`, or `interpreter` package — only `beacon-chain/`), mark it `out_of_scope`. When uncertain, treat as in-scope and attempt resolution.

    ## Step 2.5: Repository Orientation (once per batch)

    Before resolving any item, run a single Glob on `target_workspace/*/` to list top-level directories. Build a mental map of which packages handle which domains (e.g. crypto, networking, state, consensus, validation, p2p, database). Reuse this map for all items in the batch — it tells you where to narrow searches and which properties are out of scope.

    ## Step 3: Code Resolution (per in-scope item)

    For each in-scope property, follow this iterative methodology. **Do not mark `not_found` until you have tried at least 3 different search terms.**

    ### 3a. Derive Search Terms

    Before any tool call, convert spec-level names from `assertion`, `text`, and the subgraph `.mmd` file (from the 01b index) into target-language identifiers:
    - For Go targets: spec `snake_case` → `PascalCase` (e.g. `process_attestation` → `ProcessAttestation`), spec constants stay `ALL_CAPS` (e.g. `MAX_EFFECTIVE_BALANCE`).
    - Extract function names from state transitions in the `.mmd` file — these are often close to real code identifiers.
    - From the property `assertion`, pull key nouns, verbs, and domain constants.

    Produce an ordered list: most-specific identifier first (e.g. exact function name), then broader terms (root words, abbreviations, related constants).

    ### 3b. Search — Most Specific First

    Grep `target_workspace/` for the most specific identifier. If it matches function/type definitions, record the location and move on. Use Tree-sitter MCP `get_symbols` or `find_text` when a directory-scoped search is more efficient.

    ### 3c. Broaden If Needed

    If the specific term fails:
    - Try the next term in your list (root words, abbreviations, synonyms).
    - Use the repo orientation map from Step 2.5 to narrow searches to relevant directories instead of the full repo.
    - Try Tree-sitter `get_symbols` on the most likely package directory to browse available symbols.
    - Try partial/substring matches (e.g. `Attestation` instead of `ProcessAttestation`).

    ### 3d. Semantic Fallback

    If identifier-based searches fail, search for:
    - Constants or magic numbers from the spec (e.g. `4096`, `0x00000001`).
    - Comments or string literals describing the same concept.
    - Type definitions related to the data structures mentioned in the property.

    ### 3e. Resolve Implementation-Level Relatives

    After finding the primary location, search for **implementation-level code that wraps, caches, or mediates** the primary symbol. These are invisible in specs but critical for Phase 03 auditing.

    1. **Callers/wrappers**: Grep for the primary symbol name as a callee (e.g. `VerifyCellKzgProofBatch`) within the same package directory. Record any caller that adds caching, deduplication, or memoization logic as `role: "related"`.

    2. **Cache/map structures**: In the same package, Grep for `map[`, `cache`, `Cache`, `sync.Map`, `lru`, `seen` near the primary symbol's file. If a map is keyed by a subset of the primary function's inputs, record the map declaration and the key-building function as `role: "related"`.

    3. **Dedup/filter wrappers**: Grep for functions that check a set/map before calling the primary symbol (patterns like `if _, ok := seen[key]; ok { return }`). Record these as `role: "related"`.

    Keep this step lightweight: **at most 3 Grep calls per property**. Only record metadata (file, symbol, line_range) — do not extract code.

    ### 3f. Record Result

    **DO NOT read the matched files or extract code excerpts.** Only record metadata (file path, symbol name, line range).

    If all search attempts fail → mark as `not_found` with a mandatory `resolution_error` (see output schema).

  </instructions>

  <output>
    <format>JSON object with "properties_with_code" array</format>
    <schema>
      {
        "properties_with_code": [
          {
            "property_id": "PROP-...",
            "text": "...",
            "type": "invariant|precondition|postcondition|...",
            "assertion": "...",
            "severity": "Critical|High|Medium|Low",
            "covers": "FN-001",
            "reachability": { "classification": "...", "entry_points": [...], "attacker_controlled": true, "bug_bounty_scope": "..." },
            "exploitability": "...",
            "code_scope": {
              "locations": [           // empty list if out_of_scope or not_found
                {
                  "file": "relative/path/from/workspace/root.go",
                  "symbol": "FunctionOrTypeName",
                  "line_range": { "start": 42, "end": 78 },
                  "role": "primary" | "caller" | "callee" | "related",
                  "note": ""  // optional: observation about this location (e.g., "calls recompute function instead of cached accessor")
                }
              ],
              "resolution_status": "resolved" | "out_of_scope" | "not_found" | "error",
              "resolution_error": "",   // MUST be non-empty when status is "not_found" or "error" — list the identifiers searched and why they failed
              "resolution_method": "mcp_callgraph" | "mcp_simple" | "grep_fallback"  // only when resolved
            }
          }
        ]
      }
      **Note**: Pass through all property fields from the input. The `code_scope` field is the new addition.
    </schema>
    <stdout>Max 10 lines: processed count and per-status breakdown.</stdout>
    <final_line>Output File: {{OUTPUT_FILE}}</final_line>
  </output>
</task>
