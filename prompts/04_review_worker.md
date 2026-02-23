
---
Description: "[WORKER] Inline proof-based review of Phase 03 audit findings with spec cross-reference."
Usage: /04_review_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]
Example: /04_review_worker WORKER_ID=0 QUEUE_FILE=outputs/04_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=5 OUTPUT_FILE=outputs/04_PARTIAL_W0_1700000000_1.json
Language: English only.
Execution hint: This worker prompt is invoked by the phase-04 async orchestrator.
---

<task>
  <goal>Review and validate Phase 03 findings. Verify code claims, cross-reference with spec subgraphs, filter FPs, and calibrate severity.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <input type="file" id="context">{{CONTEXT_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    **YOU MUST COMPLETE ALL OF THE FOLLOWING:**
    1. Process ALL items in the batch (up to BATCH_SIZE).
    2. Verify every claim against actual code — re-read the exact lines cited.
    3. Cross-reference with specification subgraph to check design intent.
    4. Calibrate severity against `BUG_BOUNTY_SCOPE.json` and `TARGET_INFO.json`.
    5. After processing ALL items, write a JSON file to <ref id="results"/>.
    6. The JSON file MUST be written even if all items are disputed.

    **FAILURE TO WRITE THE JSON FILE IS A CRITICAL ERROR.**
  </critical_requirements>

  <review_approach>
    You are the final quality gate. Your job is to VERIFY, not re-audit.
    Phase 03 attempted to prove each property holds. Your task:
    - If Phase 03 found a vulnerability: verify the code reading is correct and the attack path is **actually exploitable right now**.
    - If Phase 03 found a potential-vulnerability: verify the uncertainty is genuine, not a misread.
    You do NOT need to re-run the 3-phase audit. Focus on verification, exploitability, and spec compliance.

    **Proof of exploitability is king.** A finding is only a real vulnerability if:
    1. The code reading is factually correct (the code does what Phase 03 says it does).
    2. The attack path is reachable with the CURRENT codebase and dependencies.
    3. No defensive pattern, library guarantee, or architectural design prevents exploitation.
    If ANY of these fail, the finding is a false positive.
  </review_approach>

  <instructions>
    1. **Read Queue**: Read <ref id="queue"/> to get `item_ids` and `context_file` path. Read <ref id="context"/> to get item data (keyed by ID). For each ID in `item_ids`, look up the item data in context.

    2. **Read Context Files** (do this ONCE at the start of the batch):
       a. Read `outputs/01b_SUBGRAPH_INDEX.json` — spec subgraph index for cross-reference.
       b. Read `outputs/BUG_BOUNTY_SCOPE.json` — severity definitions, scope rules, and
          domain-specific context (e.g., deployment share, trust model, out-of-scope components).
       c. Read `outputs/TARGET_INFO.json` — target repository/project metadata.
       All three files are **required**. If any file is missing, stop and report the error.
       Cache all files for use across all items in the batch.

    3. **For Each Item** (property_id, audit_result, text, assertion, covers, severity):

       Step A. **Parse Phase 03 Output**: Extract classification, code_path, proof_trace, attack_scenario from `audit_result`.

       Step B. **Verify Code Reading** (MANDATORY for vulnerability/potential-vulnerability):
         1. Extract file path and line range from code_path in audit_result. Prepend `target_workspace/`.
         2. Read the actual code (full function, not just flagged lines).
         3. Does proof_trace accurately describe the code's behavior?
         4. If proof_trace claims a check is MISSING: Grep for it in callers, upstream functions,
            and the surrounding package. A check may exist at a different layer.
         5. If proof_trace claims a concurrency issue (race condition, data race, deadlock):
            verify that the involved operations actually execute concurrently at runtime — check
            thread/goroutine/task spawn sites, not just whether the functions exist.
         6. Check for defensive patterns around the flagged code. Examples by language:
            - **Go**: sync.Mutex/RWMutex, sync/atomic, sync.Once, errgroup.Wait(), channel ownership
            - **Java**: synchronized, ReentrantLock, volatile, AtomicReference, ConcurrentHashMap
            - **C/C++**: pthread_mutex, std::mutex, std::atomic, memory barriers
            - **Rust**: Mutex, RwLock, Arc, ownership/borrowing guarantees
            - **Python**: threading.Lock, asyncio.Lock, GIL-protected operations
            - **General**: immutable data structures, copy-on-write, single-threaded event loops

       Step B2. **Verify Dependency Behavior** (MANDATORY when finding depends on external library behavior):
         If the proof_trace relies on how an external library/dependency behaves (e.g., "library
         rejects invalid input", "library enforces constraint X"), you MUST verify:
         1. Find the dependency version in the project's dependency manifest (e.g., `go.mod`,
            `go.sum`, `pom.xml`, `Cargo.toml`, `package.json`, `requirements.txt`) under
            `target_workspace/`.
         2. Determine whether the library's CURRENT version actually enforces the claimed constraint.
            Grep for relevant checks in vendored code or read the library's documented behavior.
         3. If the vulnerability requires a FUTURE library update to become exploitable, it is NOT
            a current vulnerability → DISPUTED_FP ("latent issue, not exploitable with current
            dependency version").
         4. If you cannot determine the library's behavior with confidence → CONFIRMED_POTENTIAL
            (not CONFIRMED_VULNERABILITY).

       Step C. **Spec Cross-Reference** (MANDATORY):
         1. From the item's `covers` field (element ID like "FN-001"), find the matching
            subgraph in the 01b index (search subgraph entries for the element ID).
         2. Read the corresponding `.mmd` file (path from index, prepend `outputs/graphs/`
            or use the full path from index).
         3. Check: Does the spec REQUIRE the behavior that Phase 03 flagged as a bug?
            - If the spec explicitly mandates this behavior → DISPUTED_FP (spec-compliant)
            - If the spec defines different requirements for different contexts (e.g., internal
              vs external callers, different protocol versions) → DISPUTED_FP (by-design)
            - If the spec is silent on this → finding remains valid
         4. Record the spec reference in reviewer_notes.

       Step D. **Check Common FP Patterns**:
         1. Phantom concurrency bugs: Phase 03 claims unguarded access but synchronization exists
         2. Misunderstood language idioms: language-specific patterns mistaken for bugs
         3. Design choices flagged as bugs: intentional pruning, eviction, short-circuit, fallback
         4. Theoretical-only exploits: attack path blocked by runtime constraints (execution order,
            type system, access control) that Phase 03 overlooked
         5. Over-scoped findings: flagged function is correct but Phase 03 speculates about
            hypothetical callers or future misuse
         6. Spec-compliant behavior: code follows spec exactly but Phase 03 thinks it's a bug
         7. Trust boundary differentiation: different trust levels for different interfaces are
            by design (e.g., local APIs vs network-facing APIs)
         8. Latent/future vulnerabilities: exploit requires a dependency upgrade, config change,
            or future code modification that has not happened yet — NOT a current vulnerability
         9. Library trust: code correctly delegates to a well-tested library and the library's
            current version handles the edge case properly

       Step E. **Calibrate Severity** (MANDATORY):
         Determine `adjusted_severity` using `BUG_BOUNTY_SCOPE.json` and `TARGET_INFO.json`:

         1. Read the `severity_classification` section for the program's severity definitions.
         2. Read `deployment_context` (if present) for deployment topology and target share.
         3. If severity is defined by deployment-wide impact (e.g., "% of users/nodes affected"):
            - Identify what fraction of the overall deployment the target project represents
              from `deployment_context.target_share.value` or similar fields.
            - A bug in a single component can only affect users/nodes of THAT component.
              The maximum severity is capped by the component's deployment share.
            - If the bug only triggers under specific conditions (certain configurations,
              specific timing, specific roles), the effective impact is further reduced.
         4. If the item's original severity exceeds the calibrated maximum → DOWNGRADE.
         5. Check `out_of_scope` and `conditional_scope` sections — if the finding falls
            under an explicitly excluded category, mark as DISPUTED_FP.

       Step F. **Determine Verdict**:
         - CONFIRMED_VULNERABILITY: Code reading verified, no spec justification, attack path
           reachable with CURRENT code and dependencies, severity calibrated
         - CONFIRMED_POTENTIAL: Uncertainty is genuine (ambiguous spec, complex concurrency),
           but exploitability cannot be confirmed or denied
         - DISPUTED_FP: Code misread, spec-compliant, defensive pattern exists, unreachable attack,
           latent issue not exploitable with current dependencies, or out-of-scope per program rules
         - DOWNGRADED: Real issue but lower severity than claimed (adjust severity and explain why)
         - NEEDS_MANUAL_REVIEW: Cannot determine with available information

    4. **Write Output**: After ALL items are processed, write a **single JSON object** to <ref id="results"/>:
       ```json
       {
         "reviewed_items": [ ...all reviewed items... ],
         "metadata": { "phase": "04", "worker_id": N, "batch_index": N,
                        "item_count": N, "timestamp": N, "processed_ids": [...] }
       }
       ```
       - The top-level structure MUST be a **JSON object** (dict), NOT a JSON array.
       - `"reviewed_items"` MUST be the key containing the flat list of all reviewed item objects.
       - This step is **MANDATORY**.

    5. **Confirm**: Print a summary and end with: `Output File: {{OUTPUT_FILE}}`
  </instructions>

  <output_schema>
    Each element of `reviewed_items`:
    ```json
    {
      "property_id": "...",
      "review_verdict": "CONFIRMED_VULNERABILITY | CONFIRMED_POTENTIAL | DISPUTED_FP | DOWNGRADED | NEEDS_MANUAL_REVIEW",
      "original_classification": "vulnerability | potential-vulnerability",
      "adjusted_severity": "Critical | High | Medium | Low | Informational",
      "reviewer_notes": "Concise explanation of verification result + spec reference + severity justification (3-5 sentences)",
      "spec_reference": "Brief spec citation if relevant, else empty string"
    }
    ```
  </output_schema>

  <quality_gates>
    1. Every reviewed_items element has exactly the 6 allowed keys (property_id, review_verdict, original_classification, adjusted_severity, reviewer_notes, spec_reference).
    2. reviewer_notes includes spec cross-reference result (even if "spec silent on this").
    3. Code was actually re-read for all vulnerability/potential-vulnerability items.
    4. DISPUTED_FP has a specific reason (not just "looks safe").
    5. adjusted_severity is justified against `BUG_BOUNTY_SCOPE.json` severity definitions.
       reviewer_notes must mention the severity reasoning.
    6. If the finding depends on external library behavior, reviewer_notes must state which
       library version was checked and whether the current version is actually affected.
  </quality_gates>
</task>

<output>
  <format>JSON object with "reviewed_items" key (NOT a JSON array)</format>
  <stdout>Max 8 lines: batch size, items processed, short status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>
