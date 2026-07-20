---
Description: "[RQ1 BASELINE - Arm A] Code-only vulnerability audit. NO specification, NO typed properties. Baseline for reviewer #1756A(1) / #1756B(5)."
Usage: "/audit_code_only WORKER_ID=... QUEUE_FILE=... CONTEXT_FILE=... OUTPUT_FILE=..."
Language: English only.
---

<task>
  <goal>Audit the target code units for security vulnerabilities using ONLY the
  code itself. You are given NO specification and NO pre-derived properties. This
  is the code-only-LLM baseline (arm A) - it isolates how much SPECA's recovery
  depends on specification anchoring versus a strong model reading code.</goal>

  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <input type="file" id="context">{{CONTEXT_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <what_you_get>
    - A batch of code units to audit (from the queue/context). Each unit is a
      code region (file + symbol) in the SAME in-scope code population arm C sees
      (built from BUG_BOUNTY_SCOPE in-scope components; see README), so recall is
      not confounded by a different code surface. The target repo is cloned under
      `target_workspace/`.
    - `outputs/TARGET_INFO.json` for repository metadata and in-scope components.
    - `outputs/BUG_BOUNTY_SCOPE.json` for severity thresholds and scope rules ONLY.
    - You DO NOT get a specification, a subgraph, or any typed property. Do not
      invent one and do not read `outputs/01e_*` / `outputs/02c_*` (absent here).
  </what_you_get>

  <method>
    Read the complete functions (not snippets), including callers and callees, and
    look for security-relevant defects directly in the code. With no property to
    check, hunt the standard vulnerability classes. For each candidate: read the
    full enforcing code and the data flow into it; establish an attacker-reachable
    path (entry point -> sink); an attacker-reachable defect is `vulnerability`;
    if no plausible attacker path exists, classify it `potential-vulnerability`. Consider at least: missing/incorrect input
    validation; integer/bounds errors; unchecked array or map access;
    concurrency/TOCTOU and cache-key/dedup-key defects; incorrect error handling;
    deserialization of untrusted data; state corruption across boundaries.
  </method>

  <fairness_constraints>
    - Same model, same target commit, same review phase (04) downstream as arms B/C.
    - Do NOT reconstruct the specification from memory or from spec-quoting comments.
      You may read the code but must not treat a cited spec clause as a property.
    - No web/spec fetch. Reason only from `target_workspace/`.
  </fairness_constraints>

  <output_schema>
    Write a single JSON object with EXACTLY two keys, matching Phase 03 so Phase 04
    consumes every arm identically (see prompts/03_auditmap_worker_inline.md):

    - "metadata": object. MUST include `"arm": "A_code_only"` and the worker id.
    - "audit_items": array. Each row MUST contain ONLY these 6 keys, nothing else
      (NO severity, confidence, code_scope, or attack_path):
        1) "property_id"      -> surrogate id "armA-<NNN>" (per-finding counter;
                                 arm A has no property, so this is a stable synthetic id)
        2) "classification"   -> one of: vulnerability | potential-vulnerability |
                                 not-a-vulnerability | informational | out-of-scope
                                 (EXACTLY these strings — the Phase 04 orchestrator
                                 routes only "vulnerability"/"potential-vulnerability"
                                 to review; any other spelling, e.g. "vulnerable",
                                 is silently passed through without FP filtering)
        3) "code_path"        -> "path/to/file.go::Symbol::Lstart-end" (primary location)
        4) "proof_trace"      -> 1-3 sentence rationale / root cause
        5) "attack_scenario"  -> only for vulnerability/potential-vulnerability, else ""
        6) "checklist_id"     -> set equal to property_id (downstream compatibility)

    Write the file even if there are no findings (empty "audit_items"). Severity is
    NOT emitted here; it is recovered downstream from BUG_BOUNTY_SCOPE severity
    thresholds, exactly as in arm C.
  </output_schema>
</task>
