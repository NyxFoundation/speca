---
Description: "[RQ1 BASELINE - Arm B] Spec-only audit. Specification + subgraph provided, but NO typed properties. Baseline for reviewer #1756A(1)."
Usage: "/audit_spec_only WORKER_ID=... QUEUE_FILE=... CONTEXT_FILE=... OUTPUT_FILE=..."
Language: English only.
---

<task>
  <goal>Audit the target code against the natural-language SPECIFICATION, WITHOUT
  the typed property vocabulary (no invariant/precondition/postcondition/trust-
  assumption typing and no Phase 02c code pre-resolution). This is the
  spec-only-no-properties baseline (arm B) - it isolates the contribution of the
  typed-property representation over "just hand the model the spec".</goal>

  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <input type="file" id="context">{{CONTEXT_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <what_you_get>
    - The relevant specification excerpt and the subgraph for each unit (from
      Phase 01a/01b, via the context file). The audit units cover the SAME code
      population arm C sees (README), so recall is not confounded.
    - The target code under `target_workspace/`, plus `TARGET_INFO.json` and
      `BUG_BOUNTY_SCOPE.json`.
    - You DO NOT get typed properties (`01e_*`) or pre-resolved code scope
      (`02c_*`). Do not read them; resolve code yourself with Read/Grep/Glob.
  </what_you_get>

  <method>
    Audit for divergences between what the specification REQUIRES and what the code
    does. With no typed property, work directly from the spec prose: from the spec
    excerpt list the concrete obligations the code must satisfy (informally - do
    NOT emit a typed property object); locate the enforcing code (full functions,
    callers/callees) via Grep/Read; for each obligation check whether the code
    satisfies it. An attacker-reachable gap is `vulnerability`; an uncertain-path
    gap is `potential-vulnerability`.
  </method>

  <fairness_constraints>
    - Same model, same target commit, same review phase (04) as arms A/C.
    - Use only the Phase 01a/01b spec/subgraph context given; do not fetch more
      spec text (arm B tests "spec without the property pipeline", not "spec + more
      retrieval"). Do not synthesize the typed property vocabulary as a workaround
      - that would collapse arm B into arm C.
  </fairness_constraints>

  <output_schema>
    Write a single JSON object with EXACTLY two keys, matching Phase 03 so Phase 04
    consumes every arm identically (see prompts/03_auditmap_worker_inline.md):

    - "metadata": object. MUST include `"arm": "B_spec_only"` and the worker id.
    - "audit_items": array. Each row MUST contain ONLY these 6 keys, nothing else
      (NO severity, confidence, code_scope, or attack_path):
        1) "property_id"      -> surrogate id "armB-<NNN>" (per-finding counter)
        2) "classification"   -> vulnerability | potential-vulnerability |
                                 not-a-vulnerability | informational | out-of-scope
                                 (EXACTLY these strings — the Phase 04 orchestrator
                                 routes only "vulnerability"/"potential-vulnerability"
                                 to review; any other spelling, e.g. "vulnerable",
                                 is silently passed through without FP filtering)
        3) "code_path"        -> "path/to/file.go::Symbol::Lstart-end"
        4) "proof_trace"      -> MUST begin with "[obligation: <the informal spec
                                 obligation that surfaced this>] " then 1-3 sentence
                                 rationale. The bracketed prefix is arm B's
                                 provenance so #103 can distinguish it from arm C's
                                 typed properties.
        5) "attack_scenario"  -> only for vulnerability/potential-vulnerability, else ""
        6) "checklist_id"     -> set equal to property_id

    Write the file even when there are no findings. Severity is recovered
    downstream from BUG_BOUNTY_SCOPE thresholds, as in arm C.
  </output_schema>
</task>
