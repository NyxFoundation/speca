
---
Description: "[WORKER] Perform inline proof-based 3-phase formal audit for a single property (no skill fork)."
Usage: "/03_auditmap_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=1] [OUTPUT_FILE=...]"
Example: "/03_auditmap_worker WORKER_ID=0 QUEUE_FILE=outputs/03_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=1 OUTPUT_FILE=outputs/03_PARTIAL_W0_1700000000_1.json"
Language: English only.
Execution hint: This worker prompt is invoked by the phase-03 async orchestrator. All audit logic is inlined (no skill fork).
---

<task>
  <goal>Execute a complete 3-phase proof-based formal audit for a single property and write the result.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <input type="file" id="context">{{CONTEXT_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    1. Process the item with FULL 3-phase analysis (no shortcuts, no early exits)
    2. Understand the code deeply before judging — read complete functions, not snippets
    3. Write JSON file to <ref id="results"/> after processing
    4. File MUST be written even if the item is skipped (out-of-scope)
  </critical_requirements>

  <severity_context>
    The `severity` field on each property was assigned using the bug bounty program's
    `severity_classification` criteria (e.g., network impact thresholds, % of validators affected).
    When assessing findings, respect these program-specific severity definitions — do not
    re-classify severity using generic heuristics.
  </severity_context>

  <audit_approach>
    **Your method: try to PROVE the property holds. Where the proof breaks, that is the bug.**

    This is the most effective way to find real vulnerabilities:
    - Proving correctness forces you to deeply understand the code
    - Every gap in the proof is a precise, verified finding
    - You cannot accidentally "find" a bug in code you misread

    Do NOT start by looking for bugs. Start by understanding what the code does and
    how it enforces the property. The bugs will reveal themselves as gaps in your proof.
  </audit_approach>

  <instructions>
    1. **Read Queue**: Read <ref id="queue"/> to get `item_ids` and `context_file` path. Read <ref id="context"/> to get item data (keyed by ID). Extract the single item by looking up the first ID.

    2. **Resolve Code Scope**:

       **Path prefix**: The target repository is cloned under `target_workspace/`. All `code_scope.locations[].file` paths from Phase 02c are relative to the repo root — prepend `target_workspace/` when reading files (e.g. `beacon-chain/core/blocks/payload.go` → `target_workspace/beacon-chain/core/blocks/payload.go`). Read `outputs/TARGET_INFO.json` for repository metadata.

       a. **Pre-resolved (preferred)**: If `item.code_scope.resolution_status == "resolved"` and `item.code_scope.locations` is not empty:
          - Use pre-resolved data from Phase 02c
          - Primary location is first item with `role == "primary"` in locations array
          - Related locations (callers, callees, state management) are available for context
          - **Read the `note` field on each location** — notes encode Phase 02c observations
            about discrepancies (e.g., which function variant a caller actually invokes).
            Treat each note as a hypothesis to verify or refute in Phase 2.
          - Use `item.code_excerpt` if available, which contains all relevant code sections

       b. **Fallback resolution**: If not pre-resolved, use Read/Grep/Glob to find code from `item.text` and `item.assertion`. Identify which code elements are responsible for enforcing this property. Extract relevant lines as `code_excerpt`.

       c. **Expand Context for State Analysis**:
          - Use Grep to find related state management code
          - Look for cache structures, concurrent access patterns
          - Include caller/callee context to understand state flow

       d. **Location metadata**: Track for output:
          - `code_scope`: {locations: [{file, symbol, line_range, role}], resolution_status}
          - `code_snippet`: actual code excerpt (primary location or combined from Phase 02c)
          - `state_context`: related state management code (cache, locks, etc.)

       e. **Skip Check**: If `code_scope.resolution_status` is `not_found`/`specification_only`/`out_of_scope`, OR all locations are external (`vendor/`, submodules), OR component mismatch:
          Create result with `classification = "out-of-scope"`, append to `results`, go to step 5.

       **Tool restriction**: Use ONLY Read, Grep, Glob, Write tools for code access.

    3. **3-Phase Proof-Based Audit**:

       Execute all three phases sequentially. **DO NOT use early exits or shortcuts.**

       ### Phase 1: Map the Property to Code

       **Objective:** Identify exactly HOW the codebase enforces this property.

       1. **Decompose the assertion**: What does the property claim? Break it into
          specific conditions (e.g., "cache key includes all inputs" → which inputs?
          which cache? which key construction?).

       2. **Read the enforcement code completely**: Read the FULL primary function
          (not just flagged lines). Read callers (at least one level up) and callees
          (at least one level down) using Grep.

       3. **Identify enforcement mechanisms**: List every code element that contributes
          to enforcing this property:
          - Guards/validation checks (what do they check? what do they miss?)
          - Locks/synchronization (what scope do they protect?)
          - Type constraints, bounds checks, SSZ max sizes
          - Trust boundaries (which components are trusted? which aren't?)
          - Spec-mandated behavior (read comments with spec pseudocode)

       4. **Document your understanding**: Before proceeding, state:
          "Property X is enforced by: mechanism M1 (file:line), M2 (file:line), ..."
          If you cannot identify ANY enforcement mechanism → that itself is a finding.

       ### Phase 2: Attempt to Prove the Property Holds

       **Objective:** Construct a proof that the property holds.
       Where the proof fails, that is your finding.

       For each enforcement mechanism from Phase 1, verify it is sufficient:

       1. **Input coverage**: Does the mechanism handle ALL possible inputs?
          - What are the valid ranges? What happens at boundaries?
          - What happens with nil/empty/maximum-size inputs?

       2. **Path coverage**: Is the mechanism applied on ALL code paths?
          - Use Grep to find all callers. Do all callers go through the guard?
          - Are there alternative construction paths (deserialization, config,
            checkpoint sync) that skip the guard?

       3. **Concurrency**: Is the mechanism valid under concurrent execution?
          - Is the protected data accessed under a lock? Verify the lock scope.
          - Is the operation init-only (runs once at startup)? If so, no race.
          - If a race is claimed, verify BOTH operations actually run concurrently
            at runtime — not just theoretically.

       4. **Temporal validity**: Does the mechanism hold over time?
          - Can the protected state become stale? When is it refreshed?
          - TOCTOU: can state change between check and use? Verify with actual
            call chain — is there a yield point between them?

       5. **Implementation pattern obligations**: If the code uses any of these
          patterns, perform the corresponding additional check:

          - **Cache/Memoization**: List every input that affects the computation's
            result. Verify each is part of the cache key. If an input is missing
            from the key, the cache can return wrong results for different inputs.
          - **Deduplication/Seen-set**: List every field that makes items semantically
            distinct. Verify each is part of the dedup key.
          - **Derived/Precomputed state**: (a) Verify the derived value is invalidated
            or recomputed when the source state changes. (b) When code has BOTH a
            cached accessor and a recompute-from-current-state function, verify
            callers use the correct one — using recompute where the spec requires
            the cached value (or vice versa) produces wrong results when the
            underlying state mutates between precomputation and use.
          - **Multi-path construction**: Verify ALL construction paths enforce the
            same invariants (ordering, bounds, uniqueness).
          - **Repeated accessor reads**: If the same getter is called multiple times
            on mutable state, verify the values cannot diverge between calls.
          - **Return value completeness**: Verify callers handle all semantic
            variants (success-true, success-false, error), not just the error case.

       6. **Write the proof**:
          - If proof succeeds: "Property holds because M1 guarantees A, M2 guarantees
            B, and A ∧ B → property." Proceed to Phase 3.
          - If proof fails at a specific point: That is your finding. Document:
            (a) which condition is not satisfied, (b) which code path violates it,
            (c) what state inconsistency results.

       ### Phase 3: Stress-Test Your Conclusion

       **Objective:** Challenge your own proof (if it succeeded) or verify your
       finding (if the proof failed). Either way, question your assumptions.

       **If your proof succeeded (you believe the property holds):**
       1. List every assumption your proof depends on. For each:
          - "This function is only called at init" → Grep for ALL callers to confirm
          - "Config is immutable at runtime" → Search for Override/Set/Update methods
          - "This lock protects the data" → Verify the lock is held at EVERY access
          - "The spec mandates this behavior" → Re-read the spec comment to confirm
          - "Function A and function B compute the same result" → Read BOTH implementations;
            verify they use the same state source, same inputs, and same algorithm.
            Similar names do not imply equivalence.
       2. If any assumption is wrong, re-do Phase 2 with corrected understanding.

       **If your proof failed (you found a potential bug):**
       1. **Verify your code reading is correct**:
          - Re-read the exact lines you cited. Does the code actually do what you claim?
          - If you claim a check is MISSING, Grep for it — it may exist in a caller
            or a different function on the same path.
          - If you claim a race condition, verify both operations run concurrently
            at runtime (not just at init or behind a lock).
       2. **Check for intentional design**:
          - Read comments near the code. Is this behavior intentional?
          - Is there a trust boundary? (local EL is trusted, spec defers some validation)
          - Does a test file exercise this exact behavior?
       3. **Construct a concrete attack path**: Trace from an external entry point
          (P2P message, RPC call) through the actual call chain to the vulnerable code.
          If you cannot construct a reachable path, downgrade to informational.

       **Classification criteria:**
       - `vulnerability`: Proof failed, code reading verified, no intentional design
         explains the gap, concrete attack path exists from external entry point.
       - `potential-vulnerability`: Proof failed, but attack reachability is uncertain
         or requires specific conditions. OR proof succeeded but an assumption is
         hard to fully verify.
       - `not-a-vulnerability`: Proof succeeded and survived stress-testing. OR proof
         failed but the gap is intentional by design/spec.
       - `out-of-scope`: Code is in external library, vendor/, or unrelated component.

    4. **Compress to 6-Field Output**: Map the analysis to the minimal schema:
       - `property_id`
       - `classification` (one of: vulnerability | potential-vulnerability | not-a-vulnerability | informational | out-of-scope)
       - `code_path` (primary location: `file::symbol::Lstart-end`)
       - `proof_trace` (succinct rationale or root cause/proof, 1-3 sentences)
       - `attack_scenario` (only for vulnerability/potential-vulnerability; else "")
       - `checklist_id` (set to property_id for downstream compatibility)

    5. **Write Output**: Write a JSON object with `metadata` and `audit_items` to <ref id="results"/>.

    6. **Confirm**: On stdout, print a one-line summary (<=3 lines total) and `Output File: {{OUTPUT_FILE}}`.
  </instructions>

  <output_schema>
    Write a single JSON object with two keys:
    - "metadata": keep the existing metadata structure (phase, worker_id, batch_index, item_count, timestamp, processed_ids, etc.) unchanged.
    - "audit_items": an array of result rows. Each row MUST contain ONLY the following keys, nothing else:
      1) "property_id"       -> the property_id string
      2) "classification"    -> one of: vulnerability | potential-vulnerability | not-a-vulnerability | informational | out-of-scope
      3) "code_path"         -> string like "path/to/file.go::FuncName::L22-33" (primary location)
      4) "proof_trace"       ->
         - if classification is vulnerability or potential-vulnerability: concise root cause statement + short proof / why the guard fails (1-3 sentences)
         - otherwise: concise rationale why it is safe or out-of-scope (1-3 sentences)
      5) "attack_scenario"   ->
         - if vulnerability/potential-vulnerability: one concrete exploit path (1-2 sentences)
         - otherwise: empty string ""
      6) "checklist_id"      -> the property_id string (for downstream compatibility)
    - Do NOT emit any other fields (no severity, confidence, bug_bounty_eligible, phases, state_context, summaries, recommendations, counts, or headers).
    - Preserve JSON ordering above for readability.
  </output_schema>

  <quality_gates>
    **Before writing output, verify:**

    1. **Field whitelist**: Every audit_items element has exactly the 6 allowed keys (property_id, classification, code_path, proof_trace, attack_scenario, checklist_id). No extras.
    2. **Non-empty rationale**: proof_trace non-empty (<= 3 sentences). attack_scenario non-empty only for vulnerability/potential-vulnerability; otherwise exactly "".
    3. **Code path present**: code_path includes file, symbol (if available), and line range e.g., `beacon-chain/core/peerdas/reconstruction.go::ReconstructDataColumnSidecars::L31-122`.
    4. **Classification sanity**: use allowed set only.
    5. **Metadata preserved**: metadata object is still included and unchanged except for fields you legitimately update (e.g., timestamp, processed_ids).
    6. **All phases executed**: Every phase (1: Map, 2: Prove, 3: Stress) must have been executed. No early exits.
  </quality_gates>

  <anti_patterns>
    **AVOID these thinking errors:**

    False negatives (missing real bugs):
    - "Guards exist → safe" — Prove guards are sufficient for ALL paths and states
    - "No counterexample found → safe" — Revisit your proof assumptions
    - "Code looks simple → skip analysis" — Complex bugs hide in simple code
    - "Function A and B produce same result → safe" — Verify same state source;
      cached/precomputed vs recomputed from mutable state are NOT equivalent

    False positives (reporting non-bugs):
    - "Check X is missing from this function" — Grep for it in callers/upstream first
    - "Race condition possible" — Verify operations actually run concurrently at RUNTIME, not just at init
    - "Cache key is incomplete" — Verify the omitted field actually varies during the cache's lifetime
    - "Path A bypasses validation" — Check if it has a different trust model (local EL, local validator)
    - "Function doesn't verify Y" — Check the spec. Y may be verified elsewhere by design
    - "Different results on different paths" — Check if paths serve different use cases (e.g., different epoch ranges)
  </anti_patterns>
</task>
