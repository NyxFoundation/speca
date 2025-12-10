


---
Description: Deploy a **property-first, pro-hacker audit** across every file under `$PATH`, using `security-agent/outputs/02_CHECKLIST.json` as the authoritative operations manual. Treat each checklist line as a security objective expressed via properties, anti-properties, attack playbooks, and observability probes. Annotate code inline and append only new findings to `security-agent/outputs/03_AUDITMAP.json`; never mutate prior records.
Usage: `/03_auditmap PATH=...`
Example: `/03_auditmap PATH="./src"`
Language: English only (instructions, annotations, summaries).
---

**Mission Mindset**

- Start from **spec properties**: translate every normative behavior in `01_SPEC.json` into a safety property and its dual anti-property before scanning code.
- Think in **attack chains**: model Nomad, Wormhole, Harmony, and Hyperlane style incident playbooks; expect multi-step exploit composition, not isolated bugs.
- Demand **observability proof**: every control must emit or reference evidence (events, metrics, logs) proving it fired.
- Enforce **cross-implementation parity**: Cairo ↔ EVM behavior must match on canonical vectors; hash/encoding drift is an exploit vector.
- Embrace **combiners & scoring**: tag satisfied predicates and auto-raise when dangerous combinations materialize.
- Default to **Cairo-first hardening**: respect Starknet-specific failure modes (felt ranges, dict defaults, dispatcher routing).

---
**Always use /serena for these development tasks to maximize token efficiency:**

## Inputs

1. **Checklist (required):** `security-agent/outputs/02_CHECKLIST.json` — source of properties, anti-properties, static rules, fuzz hooks, observability probes, combinators.
2. **Spec (context-only):** `security-agent/outputs/01_SPEC.json` — authoritative on architecture, trust assumptions, governance. Never contradict declared `trust_entities`.
3. **Property inventory (derived):** `security-agent/outputs/01_PROP.json` — For every spec behavior, record the property/anti-property pair with location, state predicate, falsification method, and evidence target.
4. **Audit target (required):** `$PATH` — audit every file recursively; zero default exclusions.
5. **Existing Audit Map (optional):** `security-agent/outputs/03_AUDITMAP.json` — append-only sink; prior entries are immutable.

---

## Doctrine & Methods (embed in every pass)

1. **Property Authoring:** Encode each property as (a) what must hold, (b) where it must hold, (c) how to falsify it (negative tests + static queries), (d) what observability proves coverage.
2. **Attack Playbook Clusters:** Translate real bridge incidents into checklist families; include Nomad acceptableRoot sentinel, Wormhole signature bypass, parity/encoding drift, Cairo felt/dict pitfalls.
3. **Algorithm Anti-Property Pipeline:** For every spec algorithm (DVN quorum, exactly-once, TYPE3 options, fee settlement), build bad-path libraries, static precondition detectors, executable properties.
4. **Cross-Implementation Differential Tests:** Maintain JSON vectors for GUID, commitment, channel keys, options, fee sweeps; fail parity checks on any divergence.
5. **Observability Contracts:** Attach event/log/metric expectations to each check; negative signals must exist for default/sentinel roots, unknown worker IDs, zero-length options, etc.
6. **Attack-Chain Scoring:** Tag checks with prerequisites/combinators; automatically elevate when combinations (e.g., UnknownWorkerID + DVNEarlyTrue) align.
7. **Elite Auditor Heuristics:** Follow passes inspired by samczsun, Tincho, and other top auditors—architecture/access control/value flow first, code later.
8. **Bridge Risk Themes:** Always enumerate initialization/sentinels, signature domain separation & dedup, ordering/exactly-once, cross-impl parity, option parsing, governance & immutability.
9. **Artifact Triplet:** For every checklist item, produce (a) static detector ID, (b) executable property or fuzz target, (c) evidence probe (event/log/metric).
10. **Research & Playbook Ingestion:** Periodically integrate surveys (SoK), Secureum contest guardrails, auditor interviews; update heuristic prompts accordingly.
11. **Cairo-First Track:** Enforce keccak parity (unless spec proves otherwise), explicit range/dict checks, dispatcher selector validation, vetted registry lookups.
12. **Contest Guard:** Keep out-of-scope filters in a preflight gate; never silence creative detections—filter only at reporting.

---

## Strict Rules

- **Checklist-driven execution:** Run every checklist `file_globs`, `patterns`, `detection_procedure`, fuzz harness, parity test exactly as written; enrich only through property derivations that map back to the same check IDs.
- **Property & anti-property tagging:** Each checklist action must reference its property/anti-property pair and specify falsification + observability plans before scanning code.
- **Playbook binding:** For incidents identified in the checklist, track sentinel values, domain separation, signer dedup, parity drift, Cairo pitfalls; document tags in annotations and JSON entries.
- **Inline OK only:** If an `ok_if` guard is satisfied, emit `@audit-ok` inline and skip JSON entries.
- **JSON parity:** Every `@audit` comment (non `@audit-ok`) must append a matching JSON object in `03_AUDITMAP.json` during the same execution; no deferral.
- **Status whitelist:** Audit map statuses are limited to `vuln` or `needs-investigation`.
- **Append-only:** When `03_AUDITMAP.json` exists, add only non-duplicate items; composite keys are immutable.
- **Path scope:** Audit all files beneath `$PATH`; infer language from extension/shebang/build metadata.
- **Observability proof:** No control is considered covered without an event/log/metric reference.
- **Attack-chain composition:** Track satisfied predicates and escalate combinations that meet defined dangerous conjunctions.
- **Ten passes:** Complete the Ten-Pass Property Audit Loop below—no early exits.
- **Call traversal:** Follow every reachable callee within `$PATH`.
- **Manual static review:** Execute every checklist step through hand-driven static inspection; usage of Segmap or similar mapping tools is forbidden.
- **Re-audit despite prior `@audit-ok`:** Treat existing annotations as historical context only. Even if an `@audit-ok` references the same checklist item—or a different checkpoint—ignore it and perform the full manual review again.
- **Honor trust assumptions:** Never raise findings contradicting explicit trust/gov assumptions in `01_SPEC.json`.
- **Artifact triplet enforcement:** Every checklist item must cite static detector, executable property, and evidence probe identifiers in annotations and JSON.
- **Cross-impl parity logging:** Document parity test coverage/outcomes in the summary section of the audit map.

---

## Inline Commenting Standard

Insert comments **directly above** the relevant code span. Use one-line tokens with explicit tagging:

- **Flag:**
  `// @audit <CHECK_ID> [vuln|needs-investigation] -- <short reason>; property=<name>; anti_property=<name>; static_detector=<id>; executable_property=<id>; evidence_probe=<event|metric>; attack_chain=<combo|none>; tags=property:<slug>,anti:<slug>,playbook:<slug>; ok_if_checked=false`

- **Safe:**
  `// @audit-ok <CHECK_ID> -- <safety rationale>; property=<name>; ok_condition=<identifier>; evidence_probe=<event|metric>; tags=property:<slug>,ok:true`

> Comments remain ASCII, concise, and one line. Record `@audit-ok` only when guards satisfy `ok_if`. Mirror every `@audit` comment with a JSON entry unless an identical composite key already exists.

---

## Ten-Pass Property Audit Loop

1. **Recon & Property Extraction:** Derive properties/anti-properties, map invariants to code locations, identify expected observability.
2. **Attack Playbook Synthesis:** Instantiate real-incident playbooks (Nomad sentinel, Wormhole bypass, parity drift, Cairo pitfalls) into checklist clusters and negative examples.
3. **Static Detector Execution:** Run regex/Semgrep/Slither/Mythril/AST rules; annotate hits; skip previously tagged spans.
4. **Executable Properties & Fuzzing:** Bind properties to fuzz/property-based tests (Echidna/Cairo equivalents); seek counterexamples; record harness IDs.
5. **Intra-Module Call Graph Pass:** Follow call chains within each module to confirm guard ordering/state transitions; note ok_if results.
6. **Cross-Module Call Graph Pass:** Traverse inter-module/inter-layer calls; validate DVN quorum flows, relayer pipelines, dispatcher routes.
7. **Dataflow & Value Flow Analysis:** Trace external inputs to sinks; enforce normalization, access control, funds/state flow invariants.
8. **Parity & Differential Testing:** Execute canonical JSON vectors across Cairo↔EVM implementations; fail on mismatch; inspect hashing/encoding parity and range/dict policies.
9. **Observability & Resilience Review:** Confirm events/metrics are emitted, negative signals exist, DoS/gas fallback handled, governance safeguards intact.
10. **Chain Composition & Gap Sweep:** Combine satisfied predicates, raise `needs-investigation` for dangerous conjunctions, and ensure 100% file/function coverage.

During each pass, verify `ok_if` conditions and upgrade/downgrade annotations accordingly.

---

## Finding Classification

- **`vuln`** — Property fails without ok_if justification; exploit is demonstrated or highly confident; provide attack chain context and severity.
- **`needs-investigation`** — Property or anti-property is suspected but impact or reachability needs confirmation; still record evidence and combinators.

Attach `attack_chain_score` (0–10) to each JSON entry to reflect composition risk, even when individual checks pass.

---

## Deduplication & Append Policy

- **Composite key:** `<check_id>|<file>|<line>|<hash(snippet)>`.
- Skip entries with existing composite keys; never edit `status`, `description`, or metadata of prior items.
- Preserve chronological integrity; append new findings only.

---

## Output: `security-agent/outputs/03_AUDITMAP.json`

Statuses remain restricted to `vuln` or `needs-investigation`.

```json
{
  "audit_items": [
    {
      "id": "auto-uuid",
      "check_id": "CL-BRIDGE-EXACTLY-ONCE-TOMBSTONE",
      "file": "contracts/Bank.sol",
      "line": 142,
      "snippet": "call.value(amount)()",
      "risk_category": "economic",
      "severity": "high",
      "property": "Exactly-once execution requires tombstone before external call",
      "anti_property": "External call can execute before tombstone commitment",
      "static_detector": "semgrep:bridge/external-call-before-state",
      "executable_property": "fuzz:exactly_once_tombstone",
      "evidence_probe": "event PacketDelivered",
      "attack_chain": ["UnknownWorkerID", "DVNEarlyTrue"],
      "attack_chain_score": 8,
      "observability": "Missing PacketCommitted -> PacketDelivered monotonic counter",
      "status": "vuln",
      "round": 4,
      "call_stack": ["withdraw()", "payout()"],
      "evidence": "no tombstone prior to external call; fuzz harness produced replay",
      "notes": "Derives from Nomad acceptableRoot playbook; requires sentinel root hardening.",
      "tags": [
        "property:exactly-once",
        "anti:replay",
        "playbook:nomad-sentinel",
        "evidence:event"
      ]
    }
  ],
  "summary": {
    "path": "$PATH",
    "rounds": 10,
    "property_pairs_total": 0,
    "property_pairs_reviewed": 0,
    "attack_chain_alerts": 0,
    "parity_vectors_tested": 0,
    "parity_vectors_failed": 0,
    "total_audit_flags": 1,
    "coverage": {
      "files_total": 0,
      "files_reviewed": 0,
      "functions_reviewed": 0
    },
    "notes": "Statuses limited to vuln / needs-investigation; OK cases are inline only."
  }
}
```

When the file already exists, append only new non-duplicate entries. Update summary counters for the current run while keeping prior rounds intact.

---

## Procedure (Step-by-step)

1. **Preflight**
   - Load `02_CHECKLIST.json`; extract properties, anti-properties, static detectors, fuzz harnesses, observability probes, combinators.
   - Read `01_SPEC.json` for architecture, trust entities, governance constraints.
   - Reconcile existing property inventory with checklist to ensure every behavior has a mapped property pair.
   - Recursively index files under `$PATH`; parse existing `@audit`/`@audit-ok` annotations to avoid duplicate tagging.
   - Load `03_AUDITMAP.json` if present to collect existing composite keys and tags.

2. **Execute the Ten-Pass Property Audit Loop**
   - During each pass, attach annotations, run static detectors, execute fuzz/property tests, parity vectors, and document observability.
   - Evaluate `ok_if` conditions promptly; convert qualifying cases to `@audit-ok` without JSON entries.
   - Maintain attack-chain state to detect dangerous combinations as passes progress.

3. **Emit / Append**
   - For every `@audit` comment, immediately append the structured entry (with property, anti_property, artifacts, observability, tags, attack_chain_score) to `03_AUDITMAP.json` unless the composite key already exists.
   - Restrict statuses to `vuln` or `needs-investigation`.
   - Update summary metrics: `rounds=10`, property coverage, attack_chain alerts, parity outcomes, coverage tallies.
   - Verify that every inline `@audit` comment has a matching JSON entry before concluding.

---
