---
Description: "[RQ1 BASELINE — Arm A] Code-only vulnerability audit. NO specification, NO typed properties. Baseline for reviewer #1756A(1) / #1756B(5)."
Usage: "/audit_code_only WORKER_ID=... QUEUE_FILE=... OUTPUT_FILE=..."
Language: English only.
---

<task>
  <goal>Audit the target code region for security vulnerabilities using ONLY the
  code itself. You are given NO specification and NO pre-derived properties. This
  is the code-only-LLM baseline (arm A) — it isolates how much SPECA's recovery
  depends on specification anchoring versus a strong model reading code.</goal>

  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <what_you_get>
    - A target code region (file + symbol + line range), cloned under `target_workspace/`.
    - `outputs/TARGET_INFO.json` for repository metadata and the in-scope component list.
    - `outputs/BUG_BOUNTY_SCOPE.json` for severity thresholds and scope rules ONLY.
    - You DO NOT get: a specification, a subgraph, or any typed property. Do not
      invent one and do not read `outputs/01e_*` / `outputs/02c_*` (they are absent
      in this arm).
  </what_you_get>

  <method>
    Read the complete functions (not snippets), including callers and callees, and
    look for security-relevant defects directly in the code. Because there is no
    property to check against, hunt for the standard code-level vulnerability
    classes. For each candidate:
    1. Read the full enforcing code and the data flow into it.
    2. Establish an attacker-reachable path to the defect (entry point → sink).
    3. If no plausible attacker path exists, downgrade to potential-vulnerability.

    Consider at least: missing/incorrect input validation; integer/bounds errors;
    unchecked array or map access; concurrency/TOCTOU and cache-key/dedup-key
    defects; incorrect error handling; deserialization of untrusted data; state
    corruption across boundaries. Judge severity ONLY with the program's
    `severity_classification` from BUG_BOUNTY_SCOPE.json — do not re-classify with
    generic heuristics.
  </method>

  <fairness_constraints>
    To keep the comparison against arms B/C honest:
    - Same model, same target commit, same review phase (04) downstream.
    - Do NOT reconstruct the specification from memory or from comments that quote
      the spec. If the code contains a spec citation in a comment, you may read the
      code but must not treat the cited spec text as a provided property.
    - No web/spec fetch. Reason from the code in `target_workspace/` only.
  </fairness_constraints>

  <output_schema>
    Write JSON to <ref id="results"/> with the SAME finding schema Phase 03 emits
    (so Phase 04 can consume all arms identically): an array of findings, each with
    `title`, `classification`, `severity`, `code_scope` {locations:[{file,symbol,
    line_range,role}], resolution_status}, `code_snippet`, `attack_path`,
    `confidence`, and `arm: "A_code_only"`. Write the file even if no finding
    (empty `findings` array). Set `detecting_property: null` for every finding
    (arm A has no property provenance — this is what the experiment measures).
  </output_schema>
</task>
