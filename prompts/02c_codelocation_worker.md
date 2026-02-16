
---
Description: [WORKER] Pre-resolve code locations for checklist items using Tree-sitter MCP call graph analysis
Usage: `/02c_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]`
Example: `/02c_worker WORKER_ID=0 QUEUE_FILE=outputs/02c_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=100 OUTPUT_FILE=outputs/02c_PARTIAL_W0_1700000000_1.json`
Language: English only.
Execution hint: This worker uses Tree-sitter MCP tools for semantic code analysis and call graph construction.
---

<task>
  <goal>For each checklist item in the batch, use Tree-sitter MCP to: 1) identify entry points, 2) build call graphs, 3) match items to code locations, 4) extract code excerpts.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    1. Process ALL items in the batch
    2. Use Tree-sitter MCP tools (mcp__tree_sitter__*) for all code analysis
    3. Build call graphs from entry points using Tree-sitter queries
    4. Match checklist items to code locations using keyword extraction and graph traversal
    5. Write JSON file to <ref id="results"/> after processing ALL items
    6. File MUST be written even if some items fail resolution
    7. Handle errors gracefully - continue processing even if individual items fail
  </critical_requirements>

  <instructions>
    ## Phase 0: Setup

    1. **Read Input**:
       - Read <ref id="queue"/> and parse JSON
       - Select first BATCH_SIZE items
       - Create empty `results = []` array

    2. **Register Target Project**:
       ```
       Use mcp__tree_sitter__register_project_tool with:
       - path: "target_workspace" (absolute path to cloned target repo)
       - name: "target-project"
       ```
       This registers the target codebase for analysis.

    ## Phase 1: Entry Point Identification

    For each unique `reachability.entry_points` category in the batch:

    **Entry Point Categories & Patterns:**

    - **P2P**: Network message handlers
      - Patterns: `Handle.*Message`, `Receive.*Block`, `Process.*Block`, `Validate.*Block`
      - Go: `func Handle`, `func Receive`, `func Process`, `func Validate`
      - File patterns: `**/p2p/**`, `**/sync/**`, `**/network/**`

    - **Transaction**: Transaction processing
      - Patterns: `Process.*Transaction`, `Validate.*Transaction`, `Apply.*Transaction`
      - Go: `func ProcessTransaction`, `func ValidateTransaction`
      - File patterns: `**/txpool/**`, `**/core/types/transaction*`, `**/core/state_transition*`

    - **EngineAPI** / **Engine API**: Engine API handlers
      - Patterns: `Engine.*`, `ForkchoiceUpdated.*`, `NewPayload.*`, `GetPayload.*`
      - Go: `func ForkchoiceUpdatedV`, `func NewPayloadV`, `func GetPayloadV`
      - File patterns: `**/eth/catalyst/**`, `**/beacon/engine/**`, `**/miner/payload*`

    - **Consensus**: Consensus layer functions
      - Patterns: `VerifyHeader.*`, `Prepare.*`, `Finalize.*`, `Seal.*`
      - Go: `func VerifyHeader`, `func Prepare`, `func Finalize`
      - File patterns: `**/consensus/**`, `**/core/headerchain*`

    - **Internal** / **Internal API** / **Internal state transition**: Internal processing
      - Patterns: `process.*`, `apply.*`, `execute.*`, `transition.*`
      - Go: `func process`, `func apply`, `func execute`
      - File patterns: `**/core/**`, `**/internal/**`

    **Tool Usage:**
    ```
    For Go codebases:
    1. List relevant files:
       mcp__tree_sitter__list_files(
         project="target-project",
         pattern="**/*.go",
         extensions=["go"]
       )

    2. For each relevant file, extract symbols:
       mcp__tree_sitter__get_symbols(
         project="target-project",
         file_path="path/to/file.go"
       )
       Returns: Dict with "functions", "classes", etc. containing symbol info

    3. Filter symbols by entry point patterns:
       - Match function names against category patterns
       - For Go: Look for exported functions (capitalized names)
       - Extract line ranges from symbol definitions
       - Store entry points: {function, file, line_start, line_end}
    ```

    **Output:**
    Create a map of entry points per category:
    ```json
    {
      "P2P": [
        {
          "function": "HandleBlockMessage",
          "file": "beacon-chain/sync/rpc_block_handler.go",
          "line_start": 45,
          "line_end": 120
        }
      ],
      "Transaction": [...]
    }
    ```

    ## Phase 2: Call Graph Construction

    For each identified entry point, build a call graph using Tree-sitter queries:

    **Tree-sitter Query for Go Call Expressions:**
    ```scheme
    (call_expression
      function: [
        (identifier) @call
        (selector_expression
          field: (field_identifier) @call)
      ])
    ```

    **Algorithm:**
    ```python
    def build_call_graph(entry_point: dict, max_depth: int = 3) -> list[dict]:
        """
        Build call graph from an entry point function.

        Args:
            entry_point: {function, file, line_start, line_end}
            max_depth: Maximum recursion depth (default: 3)

        Returns:
            List of call edges: [{from, to, file, line, depth}]
        """
        visited = set()
        call_graph = []

        def traverse(func_name: str, file_path: str, depth: int):
            if depth > max_depth or func_name in visited:
                return
            visited.add(func_name)

            try:
                # Query all function calls in the current file
                query_result = mcp__tree_sitter__run_query(
                    project="target-project",
                    query="(call_expression function: [(identifier) @call (selector_expression field: (field_identifier) @call)])",
                    file_path=file_path,
                    language="go",
                    max_results=100
                )

                # Extract called function names
                called_functions = set()
                for match in query_result.get("matches", []):
                    for capture in match.get("captures", []):
                        if capture.get("name") == "call":
                            called_func = capture.get("text", "").strip()
                            if called_func and len(called_func) > 0:
                                called_functions.add(called_func)

                # For each called function, find its definition
                for called_func in called_functions:
                    if len(call_graph) >= 50:  # Limit total edges per entry point
                        break

                    # Try to find the function definition
                    # Option 1: Use find_text with regex
                    find_results = mcp__tree_sitter__find_text(
                        project="target-project",
                        pattern=f"func\\s+({called_func}|\\([^)]+\\)\\s*{called_func})\\s*\\(",
                        use_regex=True,
                        file_pattern="**/*.go",
                        max_results=5
                    )

                    for result in find_results:
                        result_file = result.get("file", "")
                        result_line = result.get("line", 0)

                        # Verify this is actually a function definition
                        symbols = mcp__tree_sitter__get_symbols(
                            project="target-project",
                            file_path=result_file
                        )

                        # Check if the function exists in symbols
                        for func in symbols.get("functions", []):
                            if func.get("name") == called_func:
                                call_graph.append({
                                    "from": func_name,
                                    "to": called_func,
                                    "file": result_file,
                                    "line": func.get("start_line", result_line),
                                    "depth": depth + 1
                                })

                                # Recursively traverse (depth limited)
                                if depth + 1 < max_depth:
                                    traverse(called_func, result_file, depth + 1)
                                break

            except Exception as e:
                # Log error but continue
                pass

        # Start traversal from entry point
        traverse(entry_point["function"], entry_point["file"], 0)
        return call_graph
    ```

    **Simplified Alternative (if call graph is too slow):**
    ```python
    def build_simple_call_graph(entry_point: dict) -> list[dict]:
        """
        Build a simple 1-level call graph (just direct callees).
        Much faster than full recursive traversal.
        """
        call_graph = []

        try:
            # Query calls in entry point function only
            query_result = mcp__tree_sitter__run_query(
                project="target-project",
                query="(call_expression function: [(identifier) @call (selector_expression field: (field_identifier) @call)])",
                file_path=entry_point["file"],
                language="go",
                max_results=50
            )

            # Extract function names
            for match in query_result.get("matches", []):
                for capture in match.get("captures", []):
                    if capture.get("name") == "call":
                        called_func = capture.get("text", "").strip()
                        if called_func:
                            call_graph.append({
                                "from": entry_point["function"],
                                "to": called_func,
                                "file": entry_point["file"],
                                "line": 0,  # Will be resolved later if needed
                                "depth": 1
                            })

        except Exception:
            pass

        return call_graph
    ```

    **Tool Usage:**
    ```
    1. Extract function calls using Tree-sitter query:
       mcp__tree_sitter__run_query(
         project="target-project",
         query="(call_expression function: [(identifier) @call (selector_expression field: (field_identifier) @call)])",
         file_path="path/to/entry_point.go",
         language="go"
       )
       Returns: List of query matches with captured nodes

    2. Find function definitions for called functions:
       Option A - Use find_usage:
       mcp__tree_sitter__find_usage(
         project="target-project",
         symbol="FunctionName",
         language="go"
       )
       Returns: List of usage locations

       Option B - Use find_text to locate definitions:
       mcp__tree_sitter__find_text(
         project="target-project",
         pattern="func.*FunctionName",
         use_regex=true,
         file_pattern="**/*.go"
       )

    3. Verify function definitions with get_symbols:
       mcp__tree_sitter__get_symbols(
         project="target-project",
         file_path="path/to/file.go"
       )
       Returns: All symbols in file with line ranges
    ```

    **Optimization:**
    - Cache call graphs per entry point (reuse for multiple checklist items)
    - Limit max depth to 5 to prevent explosion
    - Stop traversal if visited set exceeds 1000 functions

    **Output:**
    For each entry point, store:
    ```json
    {
      "entry_point": "HandleBlockMessage",
      "entry_file": "beacon-chain/sync/rpc_block_handler.go",
      "call_graph": [
        {
          "from": "HandleBlockMessage",
          "to": "ValidateBlock",
          "file": "beacon-chain/sync/validator.go",
          "line": 45,
          "depth": 1
        },
        {
          "from": "ValidateBlock",
          "to": "ValidateRLPSize",
          "file": "core/types/block.go",
          "line": 120,
          "depth": 2
        }
      ]
    }
    ```

    ## Phase 3: Keyword Extraction and Matching

    For each checklist item:

    1. **Extract Keywords** from `test_procedure`:

       **Keyword Extraction Algorithm:**
       ```python
       import re

       def extract_keywords(test_procedure: str) -> list[str]:
           keywords = set()

           # ALL_CAPS words (constants, types)
           # Example: MAX_RLP_BLOCK_SIZE, GOSSIP_MAX_SIZE
           all_caps = re.findall(r'\b[A-Z][A-Z0-9_]{2,}\b', test_procedure)
           keywords.update(all_caps)

           # snake_case identifiers (functions, variables)
           # Example: recover_sender, state_transition, apply_withdrawals
           snake_case = re.findall(r'\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b', test_procedure)
           keywords.update(snake_case)

           # camelCase identifiers (Go: exported functions start with uppercase)
           # Example: validateBlock, processTransaction
           camel_case = re.findall(r'\b[a-z][a-z0-9]*[A-Z][a-zA-Z0-9]*\b', test_procedure)
           keywords.update(camel_case)

           # PascalCase identifiers (Go: exported types/functions)
           # Example: ProcessBlock, ValidateAttestation, ApplyTransaction
           pascal_case = re.findall(r'\b[A-Z][a-z0-9]*[A-Z][a-zA-Z0-9]*\b', test_procedure)
           keywords.update(pascal_case)

           # Technical terms (database, network, crypto, etc.)
           # Example: "signature", "hash", "merkle", "withdrawal"
           technical_terms = re.findall(r'\b(?:signature|hash|merkle|withdrawal|attestation|validator|block|transaction|state|proof|verify|validate|process|apply|execute|transition)\b', test_procedure, re.IGNORECASE)
           keywords.update([t.lower() for t in technical_terms])

           # Remove common words (stop words)
           stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might', 'must', 'can', 'to', 'of', 'in', 'for', 'on', 'at', 'by', 'with', 'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'between', 'under', 'over', 'again', 'further', 'then', 'once'}
           keywords = {k for k in keywords if k.lower() not in stop_words and len(k) > 2}

           # Sort by length (longer = more specific)
           return sorted(keywords, key=len, reverse=True)
       ```

       **Example:**
       ```
       test_procedure = "Check that MAX_RLP_BLOCK_SIZE is enforced in validateBlock()
                         and that recover_sender is called before state_transition"

       keywords = extract_keywords(test_procedure)
       # Result: ['MAX_RLP_BLOCK_SIZE', 'state_transition', 'recover_sender',
       #          'validateBlock', 'signature', 'block', 'state', 'validate']
       ```

    2. **Match Against Call Graphs**:
       For each entry point's call graph:
       - Search function names for exact keyword matches
       - Search for partial matches (e.g., "validate" matches "ValidateBlock")
       - Assign relevance scores:
         ```
         exact_match_score = 10.0
         partial_match_score = 5.0
         depth_penalty = 1.0 / (1 + depth * 0.2)
         total_score = match_score * depth_penalty
         ```

    3. **Rank Matches**:
       - Sort by total_score descending
       - Select top 5 matches
       - Include entry point itself if it matches

    4. **Extract Code Locations**:
       For each matched function:
       ```
       mcp__tree_sitter__get_symbols(
         project="target-project",
         file_path="matched_file.go"
       )

       Find the function in the symbols["functions"] list and extract:
       - file: relative path from workspace root
       - symbol: function name
       - line_range: {start: symbol.start_line, end: symbol.end_line}
       - role: "primary" (if highest score), "caller", "callee", or "related"
       ```

    5. **Extract Code Excerpts**:
       For the top 3 matches:
       ```
       mcp__tree_sitter__get_file(
         project="target-project",
         path="matched_file.go",
         start_line=line_range.start,
         max_lines=min(50, line_range.end - line_range.start + 1)
       )

       Format as:
       // PRIMARY: matched_file.go:FunctionName (lines X-Y)
       [code excerpt]

       // CALLER: caller_file.go:CallerName (lines A-B)
       [code excerpt]
       ```

    ## Phase 4: Result Assembly

    For each checklist item, create:
    ```json
    {
      "check_id": "...",
      "property_id": "...",
      "title": "...",
      ...all original fields...,
      "code_scope": {
        "entry_points_analyzed": ["HandleBlockMessage", "ProcessBlock"],
        "locations": [
          {
            "file": "core/types/block.go",
            "symbol": "ValidateRLPSize",
            "line_range": {"start": 120, "end": 145},
            "role": "primary"
          },
          {
            "file": "beacon-chain/sync/validator.go",
            "symbol": "ValidateBlock",
            "line_range": {"start": 45, "end": 78},
            "role": "caller"
          }
        ],
        "resolution_status": "resolved|not_found|no_entry_points|error",
        "resolution_error": "error message if status=error"
      },
      "code_excerpt": "// PRIMARY: core/types/block.go:ValidateRLPSize (lines 120-145)\n[code]\n\n// CALLER: beacon-chain/sync/validator.go:ValidateBlock (lines 45-78)\n[code]"
    }
    ```

    **Resolution Status Values:**
    - `resolved`: Successfully found code locations
    - `not_found`: Keywords didn't match any functions in call graphs
    - `no_entry_points`: Entry points category not found in codebase
    - `error`: Exception occurred during processing

    ## Phase 5: Error Handling & Output

    1. **Error Handling**:
       - Wrap each item processing in try-except
       - If error: set `resolution_status: "error"`, add error message, continue
       - Log errors but DO NOT stop batch processing

    2. **Write Output**:
       - After ALL items processed, write results to <ref id="results"/>
       - Format: `{"checklist_with_code": [...]}`
       - Ensure valid JSON

    3. **Print Summary**:
       ```
       Processed: 100 items
       Resolved: 75
       Not found: 15
       No entry points: 5
       Errors: 5
       Output File: {{OUTPUT_FILE}}
       ```
  </instructions>

  <simplified_approach>
    **IMPORTANT: Simplified Implementation for Reliability**

    If the full call graph analysis is too complex or fails, use this simplified approach:

    1. **Direct Symbol Search**:
       ```
       # Extract keywords from checklist item test_procedure
       keywords = extract_keywords(item.test_procedure)

       # Search for each keyword directly using find_text
       for keyword in keywords:
         results = mcp__tree_sitter__find_text(
           project="target-project",
           pattern=f"func.*{keyword}",
           use_regex=true,
           file_pattern="**/*.go",
           max_results=10
         )

         # For each match, get exact symbol definition
         for match in results:
           symbols = mcp__tree_sitter__get_symbols(
             project="target-project",
             file_path=match.file
           )
           # Extract line range and add to locations
       ```

    2. **Fallback Strategy**:
       - Try call graph analysis first (if entry_points field exists)
       - If call graph fails or takes too long (>30s): fallback to direct search
       - If direct search fails: try fuzzy matching on keywords
       - If all fails: mark as "not_found"

    3. **Performance Limits**:
       - Max 30 seconds per checklist item
       - Max 5 code locations per item
       - Max 50 lines per code excerpt
       - Skip call graph if depth would exceed 3 levels

  </simplified_approach>

  <batch_optimization>
    **Efficiency Strategies:**

    1. **Group by Entry Points Category**:
       ```
       P2P items: 40
       Transaction items: 30
       EngineAPI items: 20
       Total: 90 items

       Build call graphs once per category:
       - P2P: 5 entry points → 5 call graphs
       - Transaction: 3 entry points → 3 call graphs
       - EngineAPI: 2 entry points → 2 call graphs

       Total: 10 call graphs built
       Reused across 90 items = 9x efficiency gain
       ```

    2. **Cache Call Graphs**:
       ```python
       call_graph_cache = {}

       def get_call_graph(entry_point):
         key = f"{entry_point.file}:{entry_point.function}"
         if key not in call_graph_cache:
           call_graph_cache[key] = build_call_graph(entry_point)
         return call_graph_cache[key]
       ```

    3. **Parallel Keyword Matching**:
       - Extract keywords for all items upfront
       - Match all items against same call graph in one pass
       - Use batch symbol lookups when possible

    **Expected Performance:**
    - 100 items per batch
    - ~10 unique entry point categories
    - ~50 MCP calls total (vs. 1,000+ without optimization)
    - <3 minutes per batch
  </batch_optimization>

  <implementation_pseudocode>
    **Recommended Implementation Flow:**

    ```python
    # Phase 0: Setup
    items = read_queue(QUEUE_FILE, BATCH_SIZE)
    results = []

    # Register target project
    mcp__tree_sitter__register_project_tool(
        path=os.path.abspath("target_workspace"),
        name="target-project"
    )

    # Phase 1: Collect entry points (if using call graph approach)
    entry_point_cache = {}
    for item in items:
        if "reachability" in item and "entry_points" in item["reachability"]:
            category = item["reachability"]["entry_points"]
            if category not in entry_point_cache:
                entry_point_cache[category] = identify_entry_points(category)

    # Phase 2: Build call graphs (cached per entry point)
    call_graph_cache = {}
    for category, entry_points in entry_point_cache.items():
        for ep in entry_points[:5]:  # Limit to top 5 entry points per category
            key = f"{ep['file']}:{ep['function']}"
            if key not in call_graph_cache:
                call_graph_cache[key] = build_call_graph(ep, max_depth=3)

    # Phase 3: Process each item
    for item in items:
        try:
            # Extract keywords from test_procedure
            keywords = extract_keywords(item.get("test_procedure", ""))

            # Try call graph matching first
            locations = []
            if "reachability" in item:
                category = item["reachability"]["entry_points"]
                entry_points = entry_point_cache.get(category, [])
                for ep in entry_points:
                    key = f"{ep['file']}:{ep['function']}"
                    call_graph = call_graph_cache.get(key)
                    if call_graph:
                        matches = match_keywords_to_call_graph(keywords, call_graph)
                        locations.extend(matches[:5])

            # Fallback: Direct symbol search
            if len(locations) == 0:
                for keyword in keywords[:10]:  # Limit keywords
                    matches = mcp__tree_sitter__find_text(
                        project="target-project",
                        pattern=f"(func|type).*{keyword}",
                        use_regex=True,
                        file_pattern="**/*.go",
                        max_results=3
                    )
                    for match in matches:
                        symbols = mcp__tree_sitter__get_symbols(
                            project="target-project",
                            file_path=match["file"]
                        )
                        # Extract matching function from symbols
                        for func in symbols.get("functions", []):
                            if keyword.lower() in func["name"].lower():
                                locations.append({
                                    "file": match["file"],
                                    "symbol": func["name"],
                                    "line_range": {
                                        "start": func["start_line"],
                                        "end": func["end_line"]
                                    },
                                    "role": "primary"
                                })

            # Extract code excerpts for top 3 locations
            code_excerpts = []
            for loc in locations[:3]:
                content = mcp__tree_sitter__get_file(
                    project="target-project",
                    path=loc["file"],
                    start_line=loc["line_range"]["start"],
                    max_lines=min(50, loc["line_range"]["end"] - loc["line_range"]["start"] + 1)
                )
                code_excerpts.append(
                    f"// {loc['role'].upper()}: {loc['file']}:{loc['symbol']} "
                    f"(lines {loc['line_range']['start']}-{loc['line_range']['end']})\n"
                    f"{content}"
                )

            # Build result
            result = {
                **item,  # Keep all original fields
                "code_scope": {
                    "locations": locations[:5],
                    "resolution_status": "resolved" if locations else "not_found",
                    "resolution_error": ""
                },
                "code_excerpt": "\n\n".join(code_excerpts) if code_excerpts else ""
            }
            results.append(result)

        except Exception as e:
            # Error handling: mark as error but continue
            results.append({
                **item,
                "code_scope": {
                    "locations": [],
                    "resolution_status": "error",
                    "resolution_error": str(e)
                },
                "code_excerpt": ""
            })

    # Write output
    write_json(OUTPUT_FILE, {"checklist_with_code": results})

    # Print summary
    resolved = sum(1 for r in results if r["code_scope"]["resolution_status"] == "resolved")
    print(f"Processed: {len(results)} items")
    print(f"Resolved: {resolved}")
    print(f"Not found: {len([r for r in results if r['code_scope']['resolution_status'] == 'not_found'])}")
    print(f"Errors: {len([r for r in results if r['code_scope']['resolution_status'] == 'error'])}")
    print(f"Output File: {OUTPUT_FILE}")
    ```
  </implementation_pseudocode>

  <example_workflow>
    **Example: Batch of 15 Items**

    1. Read queue → 15 items
    2. Register project → "target-project"
    3. Group by entry_points:
       - P2P: 10 items
       - Transaction: 3 items
       - EngineAPI: 2 items

    4. Identify entry points (once per category):
       - P2P: HandleBlockMessage, ReceiveBlock, ProcessAttestation
       - Transaction: ProcessTransaction, ValidateTransaction
       - EngineAPI: ForkchoiceUpdatedV3, NewPayloadV3

    5. Build call graphs (once per entry point):
       - 7 entry points → 7 call graphs (max depth 3)
       - Cache for reuse

    6. Process items:
       For each of 15 items:
       - Extract keywords
       - Try matching against cached call graphs
       - If no match: fallback to direct symbol search
       - Extract code locations and excerpts

    7. Write results → 15 items with code_scope populated
    8. Print summary
  </example_workflow>
</task>

<output>
  <format>JSON object with "checklist_with_code" array</format>
  <schema>
    IMPORTANT: Output MUST match the Phase 02c schema exactly.

    {
      "checklist_with_code": [
        {
          // Keep ALL original fields from input checklist item
          "check_id": "string",
          "property_id": "string",
          "title": "string",
          "severity": "string",
          "reachability": {...},
          "test_procedure": "string",
          "expected_behavior": "string",
          "graph_element_under_test": "string",
          // ... all other original fields ...

          // Add/update these fields:
          "code_scope": {
            "locations": [
              {
                "file": "string (relative path from workspace root, e.g., 'core/types/block.go')",
                "symbol": "string (function/method/type name, e.g., 'ValidateRLPSize')",
                "line_range": {
                  "start": int,
                  "end": int
                },
                "role": "primary" | "caller" | "callee" | "related"
              }
            ],
            "resolution_status": "resolved" | "not_found" | "no_entry_points" | "error",
            "resolution_error": "string (only if status=error, otherwise empty string)"
          },
          "code_excerpt": "string (formatted code excerpts with markers, or empty string)"
        }
      ]
    }

    Schema Requirements:
    1. ALL original fields from input MUST be preserved
    2. code_scope.locations is a list (may be empty if not_found)
    3. code_scope.resolution_status is REQUIRED (one of: resolved, not_found, no_entry_points, error)
    4. code_scope.resolution_error is REQUIRED (empty string if no error)
    5. DO NOT add extra fields (e.g., no relevance_score, no entry_points_analyzed)
    6. line_range.start and line_range.end are both required integers
  </schema>
  <stdout>Max 10 lines: batch size, resolution stats, status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>
