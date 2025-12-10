
---
Description: Generate a comprehensive, citation-rich natural-language specification for a target project by crawling local artefacts and designated references, optionally augmented with vetted web research, and limit coverage strictly to the domain(s) explicitly provided via `CATEGORY`. Always finish by writing a syntactically valid JSON document to `security-agent/outputs/01_SPEC.json`, overwriting any prior file, and populate the `trusted_entity`, `user_flows`, and `algorithms` sections under each approved domain.
Usage: `/01_spec TARGET_DIRECTORY=... CATEGORY=... PROJECT_NAME=... [REFERENCE_URLS=...]`
Example: `/01_spec TARGET_DIRECTORY="/docs" CATEGORY="ethereum-el" PROJECT_NAME="Atlas L2" REFERENCE_URLS="https://example.com/spec,https://example.com/audit"`
Language: English only.
---

**Always use /serena for these development tasks to maximize token efficiency:**

**Goal**

Produce a specification for `$PROJECT_NAME` that covers exactly the domain(s) listed in `$CATEGORY`, focusing on exhaustive **trusted entity assumptions**, **user flows**, and **algorithms**.

* For `ethereum-el`/`ethereum-cl`, enumerate all applicable **EIPs** and reflect their normative flows and procedures, explicitly noting trust dependencies (e.g., Engine API handshakes, EL→CL payload guarantees).
* For `zk`, enumerate all **circuits** (witnesses, constraints, proving/verification, aggregation).
* For other categories, comprehensively define all functional flows and algorithms.

---

**Scope and Discovery Rules**

* Use `$TARGET_DIRECTORY` as the primary crawl root; treat each `$REFERENCE_URLS` as an additional seed.
* Generate specification content only for domain sections that match the comma-separated values in `$CATEGORY`; skip templates or placeholders for any other domain.
* Traverse Markdown, HTML, PDF, source comments, READMEs, release notes, configuration files, test fixtures, and architecture diagrams **up to depth five per domain, recursively following sublinks**.
* Mirror the repository structure, deduplicate by canonical path/heading, capture version identifiers (tags/commits/semver) with release dates for critical artefacts, and record retrieval timestamps for all external URLs.
* When `$CATEGORY` spans multiple domains, partition findings by domain and call out shared components explicitly.

---

**Web Research Expectations**

* After local crawling, search official documentation portals, RFCs, whitepapers, governance proposals (EIPs, NEPs, etc.), API references, release posts, audit reports, and bounty programs relevant to the categories.
* Prioritize: official repositories → foundations/standards → accredited audit firms → recognized bounty platforms (Immunefi, Sherlock, Code4rena, HackerOne, Bugcrowd) → high-signal community notes.
* If web access is unavailable, proceed with local materials and record the limitation in `metadata.research_notes`.

---

**Argument Reference**

* `$TARGET_DIRECTORY`: Root path with local documentation, code, specs, configuration, and tests.
* `$CATEGORY`: Comma-separated descriptors such as `ethereum-el`, `ethereum-cl`, `zk`, `blockchain`, `smart-contract`, `web`, `devops`. Lowercase kebab-case; the first value is primary, and only these values may appear as domains in the generated spec.
* `$PROJECT_NAME`: Human-readable name to appear throughout the spec.
* `$REFERENCE_URLS`: Optional absolute URLs (docs, repos, audits, RFCs) as additional crawl seeds.

---

**Category Guide**

* `ethereum-el`: Execution pipeline, EVM deltas, mempool policy, fee markets, Engine API, transaction validity, storage transitions, blob/data-availability bridges, and trusted couplings such as Engine API counterparties.
* `ethereum-cl`: Fork activation, consensus states, validator duties, Beacon APIs, DAS, sync committees, cross-layer expectations, and trusted ingestion of EL payloads/messages.
* `zk`: Circuit architecture, setup, prover/verifier roles, commitments, recursion, parameters.
* `blockchain`: Topology, networking, consensus, block structure, incentives, governance.
* `smart-contract`: Architecture, storage layout, roles, upgrades, invariants, integrations.
* `web`: Frontend/backend composition, auth, session handling, gateways, third-party services, DevSecOps lifecycle.
* `devops`: Pipelines, IaC, secrets, monitoring, compliance dependencies.

---

**Specification Targets**

* **Trusted Entities**: Enumerate every component, service, or external message stream that must be trusted, and articulate why the trust assumption holds along with explicit failure impacts. Use structured sentences with `[S#]` citations and mention both local (in-repo) and cross-layer dependencies (e.g., Engine API counterpart for EL, CL ingesting EL payload attributes). Keep focus on security posture shifts.
* **User Flows**: End-to-end interaction processes with actors, preconditions, steps, postconditions; segment flows by the exact user-triggered request or duty (e.g., `eth_transfer` vs. `contract_call` vs. `blob_tx` submission for EL RPC users, discrete validator phases for CL duties, distinct proving circuits for ZK workloads).
* **Algorithms**: Computational/cryptographic/procedural logic with pseudocode and complexity; partition entries to mirror structures found under `$TARGET_DIRECTORY` and `$REFERENCE_URLS` (e.g., module or circuit folders), and, where applicable, align Ethereum content with the governing EIP identifiers.
* Every descriptive or prescriptive sentence must be cited with `[S#]` and end with a `Sources: ...` list.

---

**Citation Policy**

* Annotate every sentence with `[S#]` tokens referencing distinct sources.
* End each narrative string with `Sources: [S1] https://..., [S2] https://...` (comma-separated, no Markdown links).
* Reuse identifiers consistently and keep them in chronological order when practical.

---

## Output Format (simple JSON example)

**File:** `security-agent/outputs/01_SPEC.json`
**Populate only the following fields** (`metadata`, per-domain `trusted_entity`, `user_flows`, `algorithms`). Generate per-domain arrays solely for the values present in `$CATEGORY`; omit any unrelated or default domains. Use this as the concrete template; expand arrays as needed. Keep each narrative block under 250 words; flag unknowns as TODO with justification and citations, but still emit a valid JSON object even when data is missing.

```json
{
  "metadata": {
    "source_directory": "$TARGET_DIRECTORY",
    "project_name": "$PROJECT_NAME",
    "spec_generated_at": "2025-10-29T08:30:00Z",
    "category": "ethereum-el",
    "reference_urls": [
      "https://example.com/spec",
      "https://example.com/audit"
    ],
    "research_notes": "Local crawl + sublinks (depth<=5). Web research prioritized official docs. [S1] Sources: [S1] https://example.com/spec, [S2] https://example.com/audit",
  },
  "trusted_entities": [
    {
      "id": "EL-TRUST-001",
      "entity": "Consensus Client Engine API Counterparty",
      "assumption": "Execution client trusts authenticated Engine API calls (e.g., `engine_forkchoiceUpdated`) to reflect the canonical forkchoice view from the paired consensus client. [S4] Sources: [S4] https://example.com/engine",
      "impact_if_compromised": "A hostile Engine API peer could inject invalid payload attributes, leading to malformed block templates or liveness failure. [S4] Sources: [S4] https://example.com/engine"
    },
    {
      "id": "EL-TRUST-002",
      "entity": "Local Fee Oracle Configuration",
      "assumption": "Node operators trust locally configured fee parameters and EIP activation flags to be current with network hardfork state. [S2] Sources: [S2] https://example.com/eips",
      "impact_if_compromised": "Stale configuration can cause rejection of valid transactions or block construction faults. [S2] Sources: [S2] https://example.com/eips"
    }
  ],
  "user_flows": [
    {
      "id": "EL-FLOW-001",
      "title": "Transaction Pool Intake and Validation (All relevant EIPs applied)",
      "actors": ["Node", "Peer", "TxPool"],
      "preconditions": [
        "Node is synced and peers are connected. [S1] Sources: [S1] https://example.com/spec"
      ],
      "steps": [
        "1. Receive raw transaction from peer or RPC; decode and sanity-check fields. [S1] Sources: [S1] https://example.com/spec",
        "2. Apply intrinsic gas, signature, nonce, and balance checks per active hardfork/EIPs. [S2] Sources: [S2] https://example.com/eips",
        "3. Enforce mempool policies (size, replacement rules, basefee awareness). [S3] Sources: [S3] https://example.com/policy"
      ],
      "postconditions": [
        "Transaction is admitted to pool, rejected with a reason, or deferred. [S1] Sources: [S1] https://example.com/spec"
      ]
    },
    {
      "id": "EL-FLOW-002",
      "title": "Block Building and Fee Market (EIP-1559 et al.)",
      "actors": ["Builder", "TxPool", "Engine API"],
      "preconditions": [
        "Parent header selected; baseFee computed from parent. [S2] Sources: [S2] https://example.com/eips"
      ],
      "steps": [
        "1. Select transactions by effective tip and constraints (gas limit, blob caps if applicable). [S2] Sources: [S2] https://example.com/eips",
        "2. Assemble block body, compute receipts/state, and header fields. [S1] Sources: [S1] https://example.com/spec",
        "3. Submit payload via Engine API for consensus coupling. [S4] Sources: [S4] https://example.com/engine"
      ],
      "postconditions": [
        "Executable payload ready for proposal/validation. [S1] Sources: [S1] https://example.com/spec"
      ]
    },
    {
      "id": "EL-FLOW-003",
      "title": "Engine API Submission and Payload Validation",
      "actors": ["Execution Client", "Consensus Client"],
      "preconditions": [
        "Consensus provides payload attributes; execution has parent state. [S4] Sources: [S4] https://example.com/engine"
      ],
      "steps": [
        "1. `engine_forkchoiceUpdated` announces head; builder returns payload ID. [S4] Sources: [S4] https://example.com/engine",
        "2. `engine_getPayload` retrieves payload; execute and verify state transitions. [S1] Sources: [S1] https://example.com/spec",
        "3. On success, mark payload valid and expose for gossip/proposal. [S4] Sources: [S4] https://example.com/engine"
      ],
      "postconditions": [
        "Validated payload is finalized for proposal path. [S4] Sources: [S4] https://example.com/engine"
      ]
    }
  ],
  "algorithms": [
    {
      "name": "EIP-1559 Base Fee Update",
      "purpose": "Adjust baseFee per block to target average gas usage. [S2] Sources: [S2] https://example.com/eips",
      "pseudocode": "`pseudo\nfunction updateBaseFee(parentBaseFee, gasUsed, gasTarget):\n  delta = parentBaseFee * (gasUsed - gasTarget) / gasTarget / BASE_FEE_MAX_CHANGE_DENOM\n  return max(0, parentBaseFee + delta)\n`[S2] Sources: [S2] https://example.com/eips",
      "complexity": "O(1)",
      "notes": "Use integer math with defined denominators; clamp underflow to zero. [S2] Sources: [S2] https://example.com/eips"
    },
    {
      "name": "Effective Gas Price (Tips + BaseFee)",
      "purpose": "Rank transactions during block selection. [S1] Sources: [S1] https://example.com/spec",
      "pseudocode": "`pseudo\neffectiveTip = min(maxFeePerGas - baseFee, maxPriorityFeePerGas)\nselectionScore = (effectiveTip, sizeHeuristic)\n`[S1] Sources: [S1] https://example.com/spec",
      "complexity": "O(1) per tx; O(n log n) for sorting",
      "notes": "Honor replacement and per-account sequencing; filter underpriced txs. [S3] Sources: [S3] https://example.com/policy"
    }
  ]
}
```

---

**User-Flow Templates**

* ethereum-el: enumerate a dedicated flow per RPC/mempool request type (e.g., `eth_transfer` submission, `contract_call` execution, blob-carrying tx path); include the canonical sequence peer discovery → tx intake → block inclusion for each variant.
* ethereum-cl: split validator responsibilities into separate flows per duty (block proposal, attestation, aggregation, sync committee, voluntary exit) with the order block generation → attestation → aggregation → finality checkpoints.
* zk: create one flow per circuit or proving program (e.g., “Circuit A proof generation”, “Circuit B proof verification”), covering witness prep → proof generation → aggregation (if any) → verifier hand-off.

**Algorithm Partition Guide**
* Mirror the directory or document granularity under `$TARGET_DIRECTORY` and `$REFERENCE_URLS` (e.g., `circuits/circuit-a`, `protocol/eip-4844`), creating one algorithm entry per module or file grouping.
* For Ethereum-related domains, title and scope each algorithm by its governing EIP (e.g., “EIP-4844 Blob Gas Accounting Algorithm”) so citations and responsibilities map cleanly to standards.
* smart-contract: admin upgrade → role-based action → failure fallback → monitoring.
* web: user auth → session issuance → API call → data persistence → audit logging.

---

**Quality and Writing Rules**

* Maintain active voice and precise terminology; place summaries before action lists.
* Declare assumptions explicitly (e.g., “Assumes prover nodes have ≥ 16 GiB RAM”) and cite supporting material.
* Keep pseudocode self-contained and specify units for constants or thresholds.
* Flag deprecated or experimental features and propose mitigations or guardrails (within notes of algorithms if relevant to execution semantics).

---

**Runtime Notes**

* Verify every cited source is reachable. If a source is private or missing, mark the relevant entry as TODO with justification in the narrative text.
* When web crawling, recursively follow links up to **five levels deep** to ensure no relevant subdocuments are missed.
* Final JSON must match the **Output Format** above; populate `user_flows` and `algorithms` exhaustively per domain (e.g., all relevant EIPs for Ethereum, all circuits for ZK).
* Before exiting, ensure `security-agent/outputs/01_SPEC.json` exists, contains valid JSON, and reflects only the requested domains; fail fast if the file cannot be written or validation fails.
