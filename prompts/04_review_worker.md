
---
Description: "[WORKER] Review Phase 03 audit findings — filter FPs, verify exploitability, calibrate severity."
Usage: /04_review_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]
Example: /04_review_worker WORKER_ID=0 QUEUE_FILE=outputs/04_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=5 OUTPUT_FILE=outputs/04_PARTIAL_W0_1700000000_1.json
Language: English only.
Execution hint: This worker prompt is invoked by the phase-04 async orchestrator.
---

<task>
  <goal>Filter false positives from Phase 03 findings, verify exploitability, calibrate severity.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <input type="file" id="context">{{CONTEXT_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    1. Process ALL items in the batch.
    2. After processing, write JSON to <ref id="results"/>. **FAILURE TO WRITE IS A CRITICAL ERROR.**
    3. The JSON file MUST be written even if all items are disputed.
  </critical_requirements>

  <instructions>

  ## 1. Setup (once per batch)

  Read <ref id="queue"/> for `item_ids` and `context_file`. Read <ref id="context"/> for item data.
  Then read and cache these files:
  - `outputs/BUG_BOUNTY_SCOPE.json` — scope rules, `trust_assumptions`, severity thresholds. **Required.**
  - `outputs/TARGET_INFO.json` — target repo metadata. **Required.**
  - For each `property_id`, locate its 01e entry in `outputs/01e_PARTIAL_*.json`.

  ## 2. For each item — FP Filter Pipeline

  Process each item through the gates below **in order**. If a gate triggers DISPUTED_FP,
  record the reason and **skip remaining gates**. This is a filter — exit early when possible.

  Items with `classification` = not-a-vulnerability, out-of-scope, or informational → **PASS_THROUGH** (skip all gates).

  ---

  ### Gate 1: Dead Code (catches bugs in unreachable code)

  Grep for call sites of the flagged function (exclude `*_test.*` / `test_*.*` files).
  - **Zero non-test callers** → DISPUTED_FP: "dead/unreachable code"
  - Function no longer exists in the file → DISPUTED_FP: "code removed"
  - Skip this gate for "missing validation" findings (the issue is that something is NOT called).

  ---

  ### Gate 2: Trust Boundary (catches findings that require compromised trusted component)

  Read `trust_assumptions` from BUG_BOUNTY_SCOPE.json. Identify which data source
  Phase 03's attack path relies on (e.g., Engine API, local IPC, P2P gossip).

  - Attack path requires data from a `SEMI_TRUSTED` or `TRUSTED` source to be
    corrupted/malicious → DISPUTED_FP: "requires compromised [source], outside security model"
  - The property may be reachable via BOTH untrusted (P2P) and trusted (EL) paths.
    If Phase 03's violation is **only** on the trusted path while the untrusted path
    is correctly validated → DISPUTED_FP for this specific violation.

  ---

  ### Gate 3: Code Verification (catches **factually incorrect** code readings only)

  Read the actual code at the flagged location (prepend `target_workspace/`).
  Read the **full function**, not just the flagged lines.

  **This gate may ONLY trigger DISPUTED_FP for objective, verifiable factual errors:**
  - The file/function Phase 03 references does not exist → DISPUTED_FP: "code does not exist"
  - The line numbers are wrong and the actual code does something completely different
    (different function, different logic) → DISPUTED_FP: "incorrect code reading — actual code at [file:line] is [what]"
  - Phase 03 claims a function calls X, but it calls Y (verifiable from source) → DISPUTED_FP: "incorrect call graph"

  **These are NOT grounds for DISPUTED_FP (record observations in reviewer_notes instead):**
  - Validation exists at a different layer / in a caller / in a parallel path → passes gate
    (note: "validation may exist at [location]" in reviewer_notes for downstream consideration)
  - Phase 03's code reading is factually correct but you disagree about security impact → passes gate
  - The behavior seems "by design" or "consistent across nodes" → passes gate
  - Defensive patterns exist (mutexes, rate limiters, etc.) → passes gate
    (note the pattern in reviewer_notes; Gate 4 handles mitigation assessment)
  - Phase 03 claims a concurrency bug and you believe it's single-threaded → passes gate
    (note the threading observation in reviewer_notes)

  ---

  ### Gate 4: Exploitability (catches findings without attacker causation)

  Determine whether an attacker can **cause** the deviation through an untrusted entry point.

  - **Attacker-triggered**: attacker controls the input that causes the deviation → passes gate.
  - **Code-intrinsic**: the code's own logic produces incorrect output regardless of input.
    No attacker action needed → DISPUTED_FP: "correctness bug, not security vulnerability"
    **Exception**: bugs that cause protocol violations (invalid blocks, wrong state transitions,
    consensus splits, data loss) ARE security vulnerabilities even without attacker input → passes gate.
  - **Defensive mitigation**: a surrounding mechanism (rate limiter, connection cap, resource
    bound) already neutralizes the attack's impact → DISPUTED_FP: "mitigated by [mechanism]"
    **Strict requirement**: The mitigation must be a **dedicated, explicit guard** (e.g., rate
    limiter with configured threshold, connection cap constant, resource pool with hard limit).
    "Validation exists at another layer" or "the crypto layer rejects it" is NOT a mitigation —
    that is defense-in-depth, which does not eliminate the underlying bug. When uncertain,
    use CONFIRMED_POTENTIAL instead of DISPUTED_FP.

  Record: "Attacker control: [direct/none]. Path: [attacker-triggered / code-intrinsic / semi-trusted]."

  ---

  ### Gate 5: Spec Cross-Reference (informational only — NO DISPUTED_FP)

  Look up the 01e entry for this `property_id`. Read `text` and `assertion`.
  Record the 01e file name and invariant text in reviewer_notes for context.

  **This gate NEVER produces DISPUTED_FP.** 01e properties are LLM-generated and may
  themselves be inaccurate. Observations go into reviewer_notes only:
  - 01e does not require the flagged behavior → note: "01e does not cover this behavior"
  - Code appears to comply with 01e → note: "code may be 01e-compliant"
  - 01e entry missing → note: "01e entry not found"

  ---

  ### Gate 6: Scope Check

  Check `out_of_scope`, `conditional_scope`, and `in_scope.scope_restriction` in BUG_BOUNTY_SCOPE.json.
  - Finding falls under an excluded category → DISPUTED_FP: "[category] is out of scope"

  ---

  ## 3. Severity Calibration (for items that passed all gates)

  Apply `severity_classification` from BUG_BOUNTY_SCOPE.json:
  1. Read impact thresholds for each severity level.
  2. If `deployment_context.client_diversity` exists, find the target's network share.
     This share caps the maximum severity for a single-component bug.
  3. If original severity exceeds the cap → DOWNGRADED.

  ## 4. Verdict

  For items that passed all gates:
  - Clear spec deviation + attacker-triggered + concrete attack path
    → **CONFIRMED_VULNERABILITY**
    (reviewer_notes MUST include: "An attacker can trigger this via [entry point]
    by [action], causing [impact].")
  - Spec deviation exists but attack path is uncertain → **CONFIRMED_POTENTIAL**
  - Cannot determine → **NEEDS_MANUAL_REVIEW**

  **Consistency rule**: The verdict must be consistent with the gate outcomes.
  - If a gate triggered DISPUTED_FP, the verdict is DISPUTED_FP.
  - If all gates passed, the verdict MUST NOT be DISPUTED_FP — even if reviewer_notes
    contain observations like "may be by design" or "defense-in-depth exists".
    Use CONFIRMED_POTENTIAL or NEEDS_MANUAL_REVIEW for uncertain cases that passed all gates.

  ## 5. Write Output

  Write a single JSON object to <ref id="results"/>:
  ```json
  {
    "reviewed_items": [
      {
        "property_id": "...",
        "review_verdict": "CONFIRMED_VULNERABILITY | CONFIRMED_POTENTIAL | DISPUTED_FP | DOWNGRADED | NEEDS_MANUAL_REVIEW | PASS_THROUGH",
        "original_classification": "vulnerability | potential-vulnerability",
        "adjusted_severity": "Critical | High | Medium | Low | Informational",
        "reviewer_notes": "3-5 sentences: gate that triggered + evidence + 01e reference + severity reasoning",
        "spec_reference": "01e invariant text or empty string"
      }
    ],
    "metadata": { "phase": "04", "worker_id": "{{WORKER_ID}}", "item_count": N, "timestamp": N, "processed_ids": [...] }
  }
  ```

  Print summary and end with: `Output File: {{OUTPUT_FILE}}`

  </instructions>

  <quality_gates>
    1. Every item has exactly the 6 keys shown in the schema.
    2. DISPUTED_FP always states WHICH gate triggered and WHY (not just "looks safe").
    3. CONFIRMED_VULNERABILITY always includes a concrete attack sentence.
    4. reviewer_notes cites 01e file name and invariant text.
    5. adjusted_severity is justified against BUG_BOUNTY_SCOPE.json thresholds.
    6. Verdict is consistent with reviewer_notes (no self-contradiction).
  </quality_gates>
</task>

<output>
  <format>JSON object with "reviewed_items" key (NOT a JSON array)</format>
  <stdout>Max 8 lines: batch size, items processed, short status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>
