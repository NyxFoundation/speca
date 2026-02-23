
---
Description: "[WORKER] Inline proof-based review of Phase 03 audit findings with spec cross-reference."
Usage: /04_review_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]
Example: /04_review_worker WORKER_ID=0 QUEUE_FILE=outputs/04_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=5 OUTPUT_FILE=outputs/04_PARTIAL_W0_1700000000_1.json
Language: English only.
Execution hint: This worker prompt is invoked by the phase-04 async orchestrator.
---

<task>
  <goal>Review and validate Phase 03 findings. Verify code claims, cross-reference with spec subgraphs, filter FPs.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <input type="file" id="context">{{CONTEXT_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    **YOU MUST COMPLETE ALL OF THE FOLLOWING:**
    1. Process ALL items in the batch (up to BATCH_SIZE).
    2. Verify every claim against actual code — re-read the exact lines cited.
    3. Cross-reference with specification subgraph to check design intent.
    4. After processing ALL items, write a JSON file to <ref id="results"/>.
    5. The JSON file MUST be written even if all items are disputed.

    **FAILURE TO WRITE THE JSON FILE IS A CRITICAL ERROR.**
  </critical_requirements>

  <review_approach>
    You are the final quality gate. Your job is to VERIFY, not re-audit.
    Phase 03 attempted to prove each property holds. Your task:
    - If Phase 03 found a vulnerability: verify the code reading is correct and the attack path is real.
    - If Phase 03 found a potential-vulnerability: verify the uncertainty is genuine, not a misread.
    You do NOT need to re-run the 3-phase audit. Focus on verification and spec compliance.
  </review_approach>

  <instructions>
    1. **Read Queue**: Read <ref id="queue"/> to get `item_ids` and `context_file` path. Read <ref id="context"/> to get item data (keyed by ID). For each ID in `item_ids`, look up the item data in context.

    2. **Read Spec Context**: Read `outputs/01b_SUBGRAPH_INDEX.json` once.
       This contains an array of specs, each with subgraph entries and mermaid_file paths.
       Cache the index for use across all items in the batch.

    3. **For Each Item** (property_id, audit_result, text, assertion, covers, severity):

       Step A. **Parse Phase 03 Output**: Extract classification, code_path, proof_trace, attack_scenario from `audit_result`.

       Step B. **Verify Code Reading** (MANDATORY for vulnerability/potential-vulnerability):
         1. Extract file path and line range from code_path in audit_result. Prepend `target_workspace/`.
         2. Read the actual code (full function, not just flagged lines).
         3. Does proof_trace accurately describe the code's behavior?
         4. If proof_trace claims a check is MISSING: Grep for it in callers/upstream.
         5. If proof_trace claims a race condition: verify both operations run concurrently at runtime.
         6. Check for defensive patterns around the flagged code:
            - sync.Mutex / sync.RWMutex held across the critical section
            - errgroup with .Wait() before reading results
            - sync/atomic operations, sync.Once for initialization
            - Channel-based ownership transfer
            - Context cancellation propagation

       Step C. **Spec Cross-Reference** (MANDATORY):
         1. From the item's `covers` field (element ID like "FN-001"), find the matching
            subgraph in the 01b index (search subgraph entries for the element ID).
         2. Read the corresponding `.mmd` file (path from index, prepend `outputs/graphs/`
            or use the full path from index).
         3. Check: Does the spec REQUIRE the behavior that Phase 03 flagged as a bug?
            - If the spec explicitly mandates this behavior → DISPUTED_FP (spec-compliant)
            - If the spec defines different validation requirements for different contexts
              (e.g., P2P vs RPC, different fork epochs) → DISPUTED_FP (by-design differentiation)
            - If the spec is silent on this → finding remains valid
         4. Record the spec reference in reviewer_notes.

       Step D. **Check Common FP Patterns**:
         1. Phantom race conditions: Phase 03 claims unguarded access but a mutex/channel/atomic exists
         2. Misunderstood language patterns: errgroup.Wait(), sync.Once, trailing-delimiter strings
         3. Design choices flagged as bugs: intentional pruning, eviction, short-circuit
         4. Theoretical-only exploits: ordering enforced by lock/channel/sequential execution
         5. Over-scoped findings: flagged function is correct but Phase 03 speculates about hypothetical callers
         6. Spec-compliant behavior: code follows spec exactly but Phase 03 thinks it's a bug
         7. Trust model differentiation: different trust levels for local EL, local validator, P2P peers are by design

       Step E. **Determine Verdict**:
         - CONFIRMED_VULNERABILITY: Code reading verified, no spec justification, attack path reachable
         - CONFIRMED_POTENTIAL: Uncertainty is genuine (ambiguous spec, complex concurrency)
         - DISPUTED_FP: Code misread, spec-compliant, defensive pattern exists, or unreachable attack
         - DOWNGRADED: Real issue but lower severity than claimed (adjust severity)
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
      "reviewer_notes": "Concise explanation of verification result + spec reference (2-4 sentences)",
      "spec_reference": "Brief spec citation if relevant, else empty string"
    }
    ```
  </output_schema>

  <quality_gates>
    1. Every reviewed_items element has exactly the 6 allowed keys (property_id, review_verdict, original_classification, adjusted_severity, reviewer_notes, spec_reference).
    2. reviewer_notes includes spec cross-reference result (even if "spec silent on this").
    3. Code was actually re-read for all vulnerability/potential-vulnerability items.
    4. DISPUTED_FP has a specific reason (not just "looks safe").
  </quality_gates>
</task>

<output>
  <format>JSON object with "reviewed_items" key (NOT a JSON array)</format>
  <stdout>Max 8 lines: batch size, items processed, short status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>
