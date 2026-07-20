
---
Description: "[WORKER] Second-opinion critique of Phase 04 confirmed findings — external search, glossary, code re-verification."
Usage: /05_critique_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]
Example: /05_critique_worker WORKER_ID=0 QUEUE_FILE=outputs/05_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=1 OUTPUT_FILE=outputs/05_PARTIAL_W0_1700000000_1.json
Language: English only.
Execution hint: This worker prompt is invoked by the phase-05 async orchestrator.
---

<task>
  <goal>Second-opinion critique of a confirmed finding: research unfamiliar terms, look for corroborating or refuting external evidence, re-verify the cited code, and emit a three-valued verdict with a full trace.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <input type="file" id="context">{{CONTEXT_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    1. Process ALL items in the batch.
    2. After processing, write JSON to <ref id="results"/>. **FAILURE TO WRITE IS A CRITICAL ERROR.**
    3. **RECALL PROTECTION**: LIKELY_FP requires CONCRETE refuting evidence —
       either an external citation (URL you actually fetched) or a code
       re-read that shows the suspect pattern does not exist. Doubt alone is
       never enough: when uncertain, keep CONFIRMED or use INSUFFICIENT_CONTEXT.
    4. **NO FABRICATED CITATIONS**: Every URL in the output must be a URL you
       actually received from WebSearch or fetched with WebFetch in THIS
       session. If the WebSearch/WebFetch tools are not available, you MUST
       set "search_backend": "none", "evidence_provenance": "internal-only",
       leave every "urls" list empty and every "source_url" empty, and say in
       the rationale that no external search was performed. Never invent a URL,
       a CVE number you did not verify, or a "known issue" you did not find.
  </critical_requirements>

  <instructions>

  ## 1. Setup (once per batch)

  Read <ref id="queue"/> for `item_ids` and `context_file`. Read <ref id="context"/> for item data.
  Then read and cache:
  - `outputs/TARGET_INFO.json` — target repo metadata (repo, commit). **Required.**

  Each item carries:
  - `review` — the Phase 04 verdict being critiqued (`review_verdict`, `reviewer_notes`)
  - `audit_result` — the original Phase 03 finding (`summary`, `attack_scenario`, `code_scope`, `audit_trail`)
  - `text` / `assertion` / `covers` / `severity` / `type` — the underlying property

  Probe once per batch whether external search is available: attempt a single
  WebSearch call. If the tool is missing or errors, operate in degraded mode
  (`search_backend: "none"`) for the whole batch as described in
  critical_requirement 4. Do not retry the probe per item.

  ## 2. For each item — Critique Pipeline (5 steps)

  ### Step 1: Unknown-term extraction

  From the finding text (`summary`, `attack_scenario`, property `text`),
  collect terms whose exact role you would need to verify before signing an
  audit report: protocol/component names, algorithm names, spec-specific
  jargon, and candidate CVE identifiers. 0-5 terms; skip generic vocabulary.

  ### Step 2: External search (glossary)

  For each term (search available only): WebSearch it in the context of the
  target project, optionally WebFetch the best 1-2 hits. Write a 1-3 sentence
  glossary definition and record the source URL you used. Also search once for
  prior art on the finding itself, e.g. `"<target> <component> <bug class>
  CVE"` or the finding summary keywords — looking for existing CVEs,
  advisories, fixed issues, or spec discussions that either corroborate or
  refute the finding. Record every search as a trace step: query, hit URLs,
  what was found, what you inferred.

  Degraded mode: build the glossary from the internal context only, with
  empty `source_url`, and record zero search-trace URLs.

  ### Step 3: Re-read the finding with the glossary

  With the glossary in mind, re-read the Phase 03 finding and Phase 04 review.
  Ask: (a) is this a duplicate of a known/fixed issue found in Step 2?
  (b) does the spec/glossary show the reported behavior is intended by design?
  (c) does the attack path still hold once the terms are correctly understood?

  ### Step 4: Code re-verification

  Using `code_scope` locations, Read the cited files in `target_workspace/`
  (Grep/Glob to relocate the symbol if line numbers drifted). Confirm the
  suspect pattern actually exists as described. Record each location you
  re-read (file, lines, one-sentence observation). If the workspace or file
  is missing, record that as the observation — do not guess.

  ### Step 5: Verdict + trace

  - Finding survives re-reading and code re-verification (or is corroborated
    by external evidence) → **CONFIRMED**
  - Concrete refuting evidence: duplicate of an already-known/fixed issue,
    documented intended behavior, or the cited code does not contain the
    suspect pattern → **LIKELY_FP** (rationale must name the evidence)
  - Cited code unreachable/missing, or the question cannot be settled with
    the available evidence → **INSUFFICIENT_CONTEXT**

  ## 3. Write Output

  Write a single JSON object to <ref id="results"/>:
  ```json
  {
    "critiqued_items": [
      {
        "property_id": "...",
        "prior_verdict": "CONFIRMED_VULNERABILITY | CONFIRMED_POTENTIAL",
        "critique_verdict": "CONFIRMED | LIKELY_FP | INSUFFICIENT_CONTEXT",
        "glossary": [
          { "term": "...", "definition": "1-3 sentences", "source_url": "https://... or empty" }
        ],
        "search_trace": [
          { "step": 1, "query": "...", "urls": ["https://..."], "found": "...", "inference": "..." }
        ],
        "code_rechecks": [
          { "file": "path/in/target_workspace", "lines": "120-160", "observation": "..." }
        ],
        "related_cves": ["CVE-XXXX-NNNNN only if actually found in Step 2"],
        "rationale": "1-3 sentences grounding the verdict in the evidence above",
        "evidence_provenance": "external+internal | internal-only",
        "search_backend": "websearch | none"
      }
    ],
    "metadata": { "phase": "05", "worker_id": "{{WORKER_ID}}", "item_count": N, "timestamp": N, "processed_ids": [...] }
  }
  ```

  Print summary and end with: `Output File: {{OUTPUT_FILE}}`

  </instructions>

  <quality_gates>
    1. Every item has all 10 keys shown in the schema.
    2. LIKELY_FP always names the concrete refuting evidence (URL or code recheck).
    3. Every URL in the output was actually returned by WebSearch or fetched by WebFetch in this session.
    4. search_backend "none" implies: no URLs anywhere, empty related_cves unless already present in the input, evidence_provenance "internal-only".
    5. Verdict is consistent with the trace — a CONFIRMED item whose code recheck failed must instead be INSUFFICIENT_CONTEXT.
  </quality_gates>
</task>

<output>
  <format>JSON object with "critiqued_items" key (NOT a JSON array)</format>
  <stdout>Max 8 lines: batch size, items processed, search availability, short status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>
