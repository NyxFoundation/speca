
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
    - If Phase 03 found a vulnerability: verify the code reading is correct and the spec deviation is real.
    - If Phase 03 found a potential-vulnerability: verify the uncertainty is genuine, not a misread.
    You do NOT need to re-run the 3-phase audit. Focus on verification and spec compliance.

    **Spec deviation is the primary criterion.** A finding is a real vulnerability if:
    1. The code reading is factually correct (the code does what Phase 03 says it does).
    2. The code deviates from the specification (01e property) in the way Phase 03 describes.
    3. The deviation has a plausible security impact (even if mitigated by other layers).

    **Defense-in-depth principle:** A downstream defense (e.g., a later validation step, a pairing
    check, a type-system constraint) does NOT make an upstream spec violation safe. Each layer of
    the specification must be independently satisfied. If the spec requires input validation at
    layer N and the code skips it, that is a vulnerability EVEN IF layer N+1 would catch some
    cases. The downstream layer may have its own bugs, may be changed later, or may not cover
    all edge cases.

    A finding is a FALSE POSITIVE only if:
    - Phase 03's code reading is factually wrong (the code does NOT do what Phase 03 claims), OR
    - The spec (01e) does NOT actually require the behavior Phase 03 flagged, OR
    - The flagged code path is genuinely unreachable (dead code, compile-time eliminated).

    Do NOT dismiss findings based on:
    - "Another layer handles it" (defense-in-depth violation)
    - "The library will reject bad input downstream" (library behavior may change)
    - "It's only exploitable under rare conditions" (rare ≠ impossible)
    - "The current configuration prevents it" (configurations change)
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
         3. Does proof_trace accurately describe the code's behavior? This is the KEY question.
            If Phase 03 misread the code (e.g., the check it claims is missing actually exists
            in the same function), that is a genuine FP. But if the code reading is correct,
            the finding stands regardless of what OTHER functions do.
         4. If proof_trace claims a check is MISSING: Grep for it in the SAME function and its
            immediate callers. Note: finding the check in a DIFFERENT layer (e.g., a downstream
            consumer) does NOT invalidate the finding — defense-in-depth requires each layer
            to independently satisfy its spec obligations.
         5. If proof_trace claims a concurrency issue (race condition, data race, deadlock):
            verify that the involved operations actually execute concurrently at runtime — check
            thread/goroutine/task spawn sites, not just whether the functions exist.
         6. Note any defensive patterns in the SAME function (not downstream), as they may
            indicate Phase 03 misread the code:

       Step B2. **Verify Dependency Behavior** (when finding involves external library behavior):
         If Phase 03's finding is about the TARGET code's own validation logic (or lack thereof),
         downstream library behavior is IRRELEVANT to the verdict. The spec requires the target
         code to validate — that obligation exists independently of what the library does.

         Only perform dependency verification when Phase 03's proof_trace ITSELF relies on a
         claim about library behavior (e.g., "library rejects invalid input"):
         1. Find the dependency version in the project's dependency manifest under `target_workspace/`.
         2. Determine whether the library's CURRENT version actually does what Phase 03 claims.
         3. Note: Even if the library currently handles the edge case, the TARGET code's spec
            obligation to validate still stands. A library handling it is a mitigating factor
            for severity, not a reason to dismiss the finding.
         4. If you cannot determine the library's behavior with confidence → CONFIRMED_POTENTIAL
            (not CONFIRMED_VULNERABILITY).

       Step C. **Spec Cross-Reference** (MANDATORY — this is the PRIMARY decision driver):
         1. Use the 01e entry for this `property_id` as the authoritative spec requirement.
            Cite the exact invariant text in reviewer_notes.
         2. Optional: If you know the `.mmd` file path for the `covers` id, you MAY open it for context,
            but 01e takes precedence. If both disagree, follow 01e and do NOT mark DISPUTED_FP.
         3. **Core question: Does the code deviate from the spec?**
            - If 01e requires behavior X and the code does NOT do X → CONFIRMED finding.
              It does not matter if another component compensates for the missing behavior.
            - If 01e requires behavior X and the code DOES do X → Phase 03 misread → DISPUTED_FP.
            - If 01e is silent on the flagged behavior → evaluate based on code reading accuracy
              (or NEEDS_MANUAL_REVIEW if 01e is entirely missing, per Step 2).
         4. Record the 01e file name and the cited invariant in reviewer_notes.

       Step D. **Check Legitimate FP Patterns** (apply ONLY when code reading is wrong):
         These patterns are valid FP reasons ONLY when Phase 03 factually misread the code:
         1. Phantom concurrency bugs: Phase 03 claims unguarded access but synchronization
            exists IN THE SAME code path (not in a different layer)
         2. Misunderstood language idioms: language-specific patterns mistaken for bugs
            (e.g., Go's nil-slice-is-valid-empty-slice)
         3. Spec-compliant behavior: code follows spec exactly but Phase 03 thinks it's a bug
         4. Dead code: the flagged path is provably unreachable (compile-time eliminated,
            feature-gated off, or behind an always-false condition)

         These patterns are NOT valid FP reasons (do NOT use them to dismiss findings):
         - "Another layer handles it" → defense-in-depth violation, finding stands
         - "Library catches it downstream" → target code's spec obligation is independent
         - "Only exploitable under rare conditions" → severity adjustment, not dismissal
         - "Design choice" → if the spec requires different behavior, the design is wrong
         - "Trust boundary" → if the spec requires validation at this boundary, it must exist

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
    - CONFIRMED_VULNERABILITY: Code reading verified AND code deviates from spec (01e).
      The spec deviation is the deciding factor — downstream mitigations affect severity,
      not the verdict.
    - CONFIRMED_POTENTIAL: Code reading is correct, spec deviation is plausible but
      ambiguous (spec is unclear, or deviation is subtle). Genuine uncertainty.
    - DISPUTED_FP: Phase 03 factually misread the code (the code actually does what the
      spec requires), OR the spec does not require the flagged behavior, OR the code path
      is provably unreachable, OR out-of-scope per bug bounty program rules.
    - DOWNGRADED: Real spec deviation but lower severity than claimed. Use this when
      downstream mitigations reduce impact (instead of dismissing as FP).
    - NEEDS_MANUAL_REVIEW: Cannot determine with available information.

    **Decision tree (follow in order):**
    1. Is Phase 03's code reading factually correct? NO → DISPUTED_FP
    2. Does 01e require the behavior that is missing/violated? NO → DISPUTED_FP
    3. Does the code deviate from the 01e requirement? NO → DISPUTED_FP
    4. Is the deviation out of scope per bug bounty rules? YES → DISPUTED_FP
    5. Is the spec deviation clear and unambiguous? YES → CONFIRMED_VULNERABILITY
    6. Otherwise → CONFIRMED_POTENTIAL

    After determining verdict, apply severity calibration (Step E) and use DOWNGRADED
    if the calibrated severity is lower than Phase 03's original.

    **Consistency rules:**
    - If reviewer_notes says "code correctly implements spec" → verdict MUST be DISPUTED_FP.
    - If reviewer_notes confirms spec deviation → verdict MUST NOT be DISPUTED_FP.
    - If 01e requires behavior X and code lacks it, DISPUTED_FP is forbidden
      (even if another layer compensates).

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
    4. DISPUTED_FP requires ONE of these specific reasons: (a) Phase 03 misread the code,
       (b) spec does not require the flagged behavior, (c) code path is provably unreachable,
       (d) out-of-scope per bug bounty program. "Downstream defense handles it" is NOT a
       valid reason for DISPUTED_FP.
    5. adjusted_severity is justified against `BUG_BOUNTY_SCOPE.json` severity definitions.
       reviewer_notes must mention the severity reasoning.
    6. If downstream mitigations exist, use DOWNGRADED (with reduced severity) instead of
       DISPUTED_FP. The spec violation itself is still a finding.
    7. DISPUTED_FP is FORBIDDEN when 01e explicitly requires the flagged behavior and the
       code deviates from it — even if another component compensates for the deviation.
  </quality_gates>
</task>

<output>
  <format>JSON object with "reviewed_items" key (NOT a JSON array)</format>
  <stdout>Max 8 lines: batch size, items processed, short status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>
