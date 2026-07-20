---
Description: "[RQ1 BASELINE — Arm B] Spec-only audit. Specification + subgraph provided, but NO typed properties. Baseline for reviewer #1756A(1)."
Usage: "/audit_spec_only WORKER_ID=... QUEUE_FILE=... CONTEXT_FILE=... OUTPUT_FILE=..."
Language: English only.
---

<task>
  <goal>Audit the target code against the natural-language SPECIFICATION, but
  WITHOUT the typed property vocabulary (no invariant/precondition/postcondition/
  trust-assumption typing and no Phase 02c code pre-resolution). This is the
  spec-only-no-properties baseline (arm B) — it isolates the contribution of the
  typed-property representation over "just hand the model the spec".</goal>

  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <input type="file" id="context">{{CONTEXT_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <what_you_get>
    - The relevant specification excerpt and the subgraph for this region
      (from Phase 01a/01b), via the context file.
    - The target code under `target_workspace/`, plus `TARGET_INFO.json` and
      `BUG_BOUNTY_SCOPE.json`.
    - You DO NOT get: typed properties (`01e_*`) or pre-resolved code scope
      (`02c_*`). Do not read those outputs; they are absent in this arm. Resolve
      code yourself with Read/Grep/Glob from the spec excerpt.
  </what_you_get>

  <method>
    Audit for divergences between what the specification REQUIRES and what the code
    does. Because you have no typed property to check, work directly from the spec
    prose:
    1. From the spec excerpt, list the concrete obligations the code must satisfy
       (informally — do NOT emit a typed property object).
    2. Locate the enforcing code (full functions, callers/callees) via Grep/Read.
    3. For each obligation, check whether the code satisfies it; a gap that is
       attacker-reachable is a finding, else potential-vulnerability.
    Severity ONLY from the program's `severity_classification`.
  </method>

  <fairness_constraints>
    - Same model, same target commit, same review phase (04) as arms A/C.
    - Use the spec excerpt as given; do not fetch additional spec text beyond the
      Phase 01a/01b context (arm B tests "spec without the property pipeline",
      not "spec + more retrieval").
    - Do not synthesize the typed property vocabulary as a workaround — that would
      collapse arm B into arm C.
  </fairness_constraints>

  <output_schema>
    Write JSON to <ref id="results"/> in the SAME finding schema Phase 03 emits, so
    Phase 04 consumes all arms identically. Each finding: `title`, `classification`,
    `severity`, `code_scope`, `code_snippet`, `attack_path`, `confidence`, and
    `arm: "B_spec_only"`. Set `detecting_property` to the informal spec obligation
    string that surfaced the finding (NOT a typed property id) so #103's auto/expert
    analysis can distinguish arm-B provenance from arm-C typed properties. Write the
    file even when there are no findings.
  </output_schema>
</task>
