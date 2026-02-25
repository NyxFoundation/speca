
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

    **Scope of defense-in-depth:** This principle applies to INPUT VALIDATION paths — code that
    processes data from external or untrusted sources (P2P messages, public RPC, gossip).
    For INTERNAL CONSTRUCTION code (functions that assemble/build data structures from
    locally-computed values), the principle does not apply: a spec deviation in assembly logic
    is a correctness bug, not a security vulnerability, because no attacker can control
    the construction inputs. Similarly, semi-trusted boundary issues (e.g., local IPC,
    internal engine APIs) require a compromised local component as a prerequisite, which
    places them outside the security model.
  </review_approach>

  <instructions>
    1. **Read Queue**: Read <ref id="queue"/> to get `item_ids` and `context_file` path. Read <ref id="context"/> to get item data (keyed by ID). For each ID in `item_ids`, look up the item data in context.

  2. **Read Context Files** (do this ONCE at the start of the batch):
     a. Read `outputs/BUG_BOUNTY_SCOPE.json` — severity definitions, scope rules, and
        domain-specific context (e.g., deployment share, trust model, out-of-scope components).
     b. Read `outputs/TARGET_INFO.json` — target repository/project metadata.
     These two files are **required**. If either is missing, stop and report the error.
     c. For each `property_id` in the batch, you MUST locate the matching 01e output
        (e.g., `outputs/01e_PARTIAL_*.json` or `outputs/01e_CONTEXT_*.json`) that contains that `property_id`.
        If no 01e file contains the property, mark that item as `NEEDS_MANUAL_REVIEW` with reason "01e missing".
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
         1. Use the 01e entry for this `property_id` as the authoritative spec requirement.
            Cite the exact invariant text in reviewer_notes.
         2. Optional: If you know the `.mmd` file path for the `covers` id, you MAY open it for context,
            but 01e takes precedence. If both disagree, follow 01e and do NOT mark DISPUTED_FP.
         3. Decide: Does 01e REQUIRE the behavior Phase 03 flagged as a bug?
            - If 01e explicitly mandates the behavior → the code must meet it; otherwise it is a real issue.
            - If 01e is silent or missing → treat as normal (or NEEDS_MANUAL_REVIEW if missing, per Step 2).
         4. Record the 01e file name and the cited invariant in reviewer_notes.

       Step C2. **Causal Exploitability Verification** (MANDATORY):
         Step C confirmed a spec deviation exists. Now determine whether an attacker can CAUSE it.

         1. **Identify the deviation trigger**: What specific input values or conditions
            cause the code to deviate from the spec? (e.g., "count >= MAX", "array length
            mismatch", "missing validation call")
         2. **Trace attacker control to the trigger**: Can an external attacker, through an
            untrusted entry point (network API, public RPC, file upload, gossip protocol),
            control the SPECIFIC values that cause the deviation?
            - "The code path is reachable from an external interface" is NOT sufficient.
            - The question is: does the attacker's input DIRECTLY CAUSE the deviation?
            - Example YES: Attacker sends `item_count=2^32` via network API → integer
              overflow → infinite loop. The attacker controls the value that triggers the bug.
            - Example NO: Internal builder function includes all entries instead of filtering
              by criteria. Even with valid external input, the code's own logic produces
              incorrect output. The attacker doesn't control the construction logic.
         3. **Classify the code path**:
            a. **Attacker-triggered deviation**: Attacker controls the input values that cause
               the spec deviation. → Eligible for CONFIRMED_VULNERABILITY.
            b. **Code-intrinsic deviation**: The deviation is caused by the code's own
               construction/assembly logic regardless of attacker input. The code would produce
               incorrect output even with perfectly valid input. → DISPUTED_FP. This is a
               correctness bug, not a security vulnerability.
            c. **Semi-trusted boundary**: The deviation requires input from a semi-trusted
               source (local engine API, local IPC, co-located service). Exploitation requires
               compromising a co-located component first. → DISPUTED_FP. The prerequisite
               attack is outside the security model.
         4. **Record in reviewer_notes**:
            "Attacker control: [direct/none/indirect]. Path type: [attacker-triggered /
             code-intrinsic / semi-trusted]. [1 sentence justification]."

         IMPORTANT: A spec deviation without attacker causation is a correctness bug, not a
         security finding. Code-intrinsic and semi-trusted deviations → DISPUTED_FP.

       Step D. **Check Common FP Patterns**:
         1. Phantom concurrency bugs: Phase 03 claims unguarded access but synchronization exists
         2. Misunderstood language idioms: language-specific patterns mistaken for bugs
         3. Design choices flagged as bugs: intentional pruning, eviction, short-circuit, fallback
         4. Theoretical-only exploits: attack path blocked by runtime constraints (execution order,
            type system, access control) that Phase 03 overlooked
         5. Over-scoped findings: flagged function is correct but Phase 03 speculates about
            hypothetical callers or future misuse
         6. Spec-compliant behavior: code follows spec exactly but Phase 03 thinks it's a bug
         7. Trust boundary differentiation: handled by Step C2 (semi-trusted classification).
            If Step C2 already classified the path, do not duplicate analysis here
         8. Latent/future vulnerabilities: exploit requires a dependency upgrade, config change,
            or future code modification that has not happened yet — NOT a current vulnerability
         9. Library trust: code correctly delegates to a well-tested library and the library's
            current version handles the edge case properly

       Step E. **Calibrate Severity** (MANDATORY):
         Determine `adjusted_severity` by strictly applying `BUG_BOUNTY_SCOPE.json`:

         1. Read the `severity_classification` section. Each severity level has an explicit
            impact threshold (e.g., ">33% of network", ">5% of network"). These thresholds
            are the ONLY criteria — do not invent your own severity reasoning.
         2. Read `deployment_context.client_diversity` to find the target project's share.
            Match the target from `TARGET_INFO.json` (e.g., repo name) to a client entry.
            This share is the MAXIMUM network-wide impact for a single-component bug.
         3. Determine the severity cap:
            - Compare the target's share against EACH threshold in `severity_classification`.
            - The highest severity whose threshold the share EXCEEDS is the cap.
            - Example: share=31%, thresholds are Critical >50%, High >33%, Medium >5%
              → 31% > 5% but 31% < 33% → cap is **Medium**.
         4. Apply the cap:
            - If the bug affects ALL nodes of the target component → severity = cap.
            - If the bug only triggers under specific conditions (certain configurations,
              specific timing, specific roles, requires attacker-controlled input beyond
              normal operation), the effective impact is LOWER than the cap.
            - Do NOT inflate severity by speculating about multi-client composition,
              widespread propagation, or cascading effects. Evaluate the single-component
              impact as-is.
         5. If the item's original severity exceeds the calibrated result → DOWNGRADE.
         6. Check `out_of_scope` and `conditional_scope` sections — if the finding falls
            under an explicitly excluded category, mark as DISPUTED_FP.

  Step F. **Determine Verdict**:
    This decision tree applies to items with original_classification = vulnerability or
    potential-vulnerability. Items classified as not-a-vulnerability, out-of-scope, or
    informational are PASS_THROUGH (early exit — no further analysis needed).

    **Decision tree (follow in order):**
    1. Is Phase 03's code reading factually correct? NO → DISPUTED_FP
    2. Does 01e require the behavior that is missing/violated? NO → DISPUTED_FP
    3. Does the code deviate from the 01e requirement? NO → DISPUTED_FP
    4. Is the deviation out of scope per bug bounty rules? YES → DISPUTED_FP
    5. Is the deviation attacker-triggered (Step C2 type a)?
       - YES, and spec deviation is clear → CONFIRMED_VULNERABILITY
         (reviewer_notes MUST include: "An attacker can trigger this via [entry point]
         by [sending/providing X], causing [impact]." If you cannot write this sentence,
         use DOWNGRADED or CONFIRMED_POTENTIAL instead.)
       - YES, but spec deviation is ambiguous → CONFIRMED_POTENTIAL
    6. Is the deviation code-intrinsic (Step C2 type b) or semi-trusted (Step C2 type c)?
       → DISPUTED_FP (correctness bug without attacker causation, not a security finding)
    7. Otherwise → CONFIRMED_POTENTIAL
    8. Cannot determine with available information → NEEDS_MANUAL_REVIEW

    **Consistency rule:** The verdict MUST be consistent with reviewer_notes.
    - If reviewer_notes concludes "by design", "intentional", "spec-compliant",
      or "not exploitable" → verdict MUST be DISPUTED_FP.
      Do NOT use CONFIRMED_VULNERABILITY or CONFIRMED_POTENTIAL with such conclusions.
    - If reviewer_notes confirms exploitability → verdict MUST NOT be DISPUTED_FP.
    - If 01e states a required behavior and the code violates it via an attacker-triggered
      path, DISPUTED_FP is forbidden. Code-intrinsic and semi-trusted deviations are
      DISPUTED_FP regardless of 01e requirement (correctness bug, not security finding).

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
    2. reviewer_notes cites the 01e file (name) and the specific invariant text used.
    3. Code was actually re-read for all vulnerability/potential-vulnerability items.
    4. DISPUTED_FP has a specific reason (not just "looks safe").
    5. adjusted_severity is justified against `BUG_BOUNTY_SCOPE.json` severity definitions.
       reviewer_notes must mention the severity reasoning.
    6. If the finding depends on external library behavior, reviewer_notes must state which
       library version was checked and whether the current version is actually affected.
    7. DISPUTED_FP is not allowed when 01e explicitly requires the flagged behavior and the code deviates from it.
    8. CONFIRMED_VULNERABILITY requires a concrete attacker-triggered attack path in
       reviewer_notes: "An attacker can trigger this via [entry point] by [action],
       causing [impact]." Absence of this sentence invalidates the verdict.
    9. For code-intrinsic or semi-trusted deviations: CONFIRMED_VULNERABILITY, CONFIRMED_POTENTIAL,
       and DOWNGRADED are all forbidden. Use DISPUTED_FP (correctness bug, not security finding).
  </quality_gates>
</task>

<output>
  <format>JSON object with "reviewed_items" key (NOT a JSON array)</format>
  <stdout>Max 8 lines: batch size, items processed, short status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>
