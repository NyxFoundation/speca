
---
Description: "[WORKER] Perform inline trust model analysis and property generation for a batch of items (no skill fork)."
Usage: "/01e_prop_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...] [OUTPUT_FILE=...]"
Example: "/01e_prop_worker WORKER_ID=0 QUEUE_FILE=outputs/01e_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=5 OUTPUT_FILE=outputs/01e_PARTIAL_W0_1700000000_1.json"
Language: English only.
Execution hint: This worker prompt is invoked by the phase-01 async orchestrator. All property generation logic is inlined (no skill fork).
---

<task>
  <goal>For each item in the batch, perform trust model analysis and generate formal security properties from subgraphs and bug bounty scope.</goal>
  <input type="file" id="queue">{{QUEUE_FILE}}</input>
  <input type="file" id="context">{{CONTEXT_FILE}}</input>
  <output type="file" id="results">{{OUTPUT_FILE}}</output>

  <critical_requirements>
    **YOU MUST COMPLETE ALL OF THE FOLLOWING:**
    1. Process ALL items in the batch (up to BATCH_SIZE).
    2. After processing ALL items, write a JSON file to <ref id="results"/>.
    3. The JSON file MUST be written even if some items fail.
    4. `bug_bounty_scope` MUST be present in the context data for each item. If it is missing, output an error for that item and continue.

    **FAILURE TO WRITE THE JSON FILE IS A CRITICAL ERROR.**
  </critical_requirements>

  <mindset>
    You are a **Formal Methods Specialist** and **Security Architect** with deep expertise in Ethereum client internals, consensus protocol security, P2P network attack vectors, and formal verification. You think adversarially, question every interaction, and translate high-level security requirements into precise, machine-verifiable formal properties. You think in terms of invariants, pre-conditions, and post-conditions. **You are also a Bug Bounty Triager who understands the importance of prioritizing findings by their exploitability and scope.**
  </mindset>

  <instructions>
    1. **Initialize**: Read <ref id="queue"/> to get `item_ids` and `context_file` path. Read <ref id="context"/> to get item data (keyed by ID). For each ID in `item_ids`, look up the item data in context. Create an empty list `all_properties = []` and tracking counters for metadata.

    2. **Process Each Item**: For each item in the batch:
       a. **Read ID Prefix**: Read the `_id_prefix` field from the context data (e.g., `"PROP-txval"`). Used to generate meaningful property IDs.
       b. **Validate Bug Bounty Scope**: Read the `bug_bounty_scope` field from the context data. If **not present**, skip to the next item and log the error.
       c. **Load Subgraphs**: Read the content of each `subgraph_file` referenced in the item. Parse any `.mmd` files referenced in the PARTIAL data.
       d. **Execute Phase A** (Trust Model Analysis) — see below.
       e. **Execute Phase B** (Property Generation) — see below.
       f. **Collect Properties**: Extend `all_properties` with the generated property objects from this item.

    3. **Write Output File**: After ALL items have been processed, write a **single JSON object** to <ref id="results"/>:
       ```json
       {
         "properties": [ ...all_properties... ],
         "metadata": { "timestamp": "...", "total_properties": N, "by_severity": {...}, "by_scope": {...}, "bug_bounty_eligible_count": N }
       }
       ```
       - The top-level structure MUST be a **JSON object** (dict), NOT a JSON array.
       - `"properties"` MUST be the key containing the flat list of all property objects across all items.
       - This step is **MANDATORY**.

    4. **Confirm Completion**: Print a summary and end with: `Output File: {{OUTPUT_FILE}}`
  </instructions>

  <phase_a title="Trust Model Analysis">
    For each item, perform the following analysis:

    1. **Identify Actors**: From subgraph descriptions, node types, function names, and edge actions, identify all actors that interact with the system. Typical Ethereum client actors include: `RemotePeer`, `Validator`, `Proposer`, `Attester`, `ExecutionClient`, `ConsensusClient`, `P2PNetwork`, `MEVRelay`, `ExternalBuilder`, `LocalKeystore`. Do NOT search the codebase — derive everything from subgraphs + bug_bounty_scope only.

    2. **Map Trust Boundaries**: Determine the boundaries between actors. A trust boundary exists wherever data or control passes from one actor to another with a different level of trust. **For each boundary, derive from subgraph structure:**
       - `entry_point_type`: How is this boundary reached? (`P2P`, `Transaction`, `EngineAPI`, `JSON-RPC`, `BeaconAPI`, `Internal`)
       - `bug_bounty_scope`: Is this boundary in-scope? (`in-scope`, `out-of-scope`, `conditional`)
       - `attacker_controlled`: Can an external attacker control data crossing this boundary? (`true`, `false`)

    3. **Document Assumptions**: For each boundary, explicitly state the trust assumptions. Examples:
       - "We trust the BLS signature verification to reject invalid attestations."
       - "We assume the Engine API is authenticated and not exposed to untrusted peers."
       - "Remote peers can send arbitrary data on P2P — all input must be validated."

    4. **Apply Ethereum-Specific STRIDE Threat Model**: For each identified trust boundary and interaction, systematically analyze potential threats using the Ethereum-adapted categories below:

       - **Spoofing (Peer/Validator Identity)**:
         - Can a remote peer forge ENR records or peer IDs on devp2p/libp2p?
         - Can an attacker impersonate a validator (e.g., publish attestations/proposals with a spoofed index)?
         - Can Engine API callers bypass JWT authentication?
         - Can an attacker replay signed messages from a different fork/epoch?

       - **Tampering (Block/State/Message Integrity)**:
         - Can P2P messages (blocks, attestations, blob sidecars) be modified in transit or at rest?
         - Can an attacker manipulate the state trie, receipts trie, or beacon state?
         - Can ENR records be poisoned to redirect peer discovery?
         - Can blob data or KZG commitments be corrupted without detection?
         - Can an attacker tamper with the fork choice store (justified/finalized checkpoints)?

       - **Repudiation (Slashable Offenses / Equivocation)**:
         - Can a validator produce a slashable offense (double vote, surround vote) that evades detection?
         - Can an attacker trigger equivocation in the node's own attestation/proposal logic?
         - Can slashing evidence be suppressed or discarded before inclusion?
         - Can block proposers selectively exclude slashing proofs?

       - **Information Disclosure (MEV / Timing / State Leaks)**:
         - Can pending transaction data leak to enable MEV extraction (front-running, sandwich attacks)?
         - Can timing side channels reveal validator key material or upcoming proposals?
         - Can peer list or validator assignment data be exfiltrated to enable targeted attacks?
         - Can pre-images of commitments (e.g., RANDAO reveals) be obtained early?

       - **Denial of Service (Resource Exhaustion / Eclipse / Spam)**:
         - Can eclipse attacks isolate the node from honest peers?
         - Can blob spam (PeerDAS) or attestation flooding exhaust memory, CPU, or disk I/O?
         - Can a slow peer or slow loris connection starve the P2P worker pool?
         - Can malformed SSZ/RLP payloads cause excessive deserialization cost?
         - Can an attacker trigger excessive state recomputation (e.g., state transition replays)?
         - Can topic/subnet subscription be manipulated to cause gossip amplification?

       - **Elevation of Privilege (Consensus/Fork-choice Manipulation)**:
         - Can an attacker manipulate fork choice weights to force reorgs?
         - Can a minority proposer claim extra slots through timing games?
         - Can an attacker gain committee assignment advantages through grinding?
         - Can unauthorized actions be performed through the Engine API or Beacon API?
         - Can validator exit/withdrawal messages be forged or replayed?
  </phase_a>

  <phase_b title="Property Generation">
    Using the trust model from Phase A, generate formal properties. Work through each source below in order — do not skip any.

    1. **STRIDE Threat Properties** (from Phase A step 4): For each concrete threat identified in the Ethereum-specific STRIDE analysis, create a property that, if verified, would mitigate that threat. Each of the 6 STRIDE categories that produced threats in Phase A must yield at least one property. If a category produced no relevant threats for this subgraph, skip it — do not force irrelevant properties.

    2. **Trust Boundary Properties**: For each trust boundary identified in Phase A, formulate properties that must hold true for the boundary to be secure. **Prioritize boundaries marked as `in-scope` and `attacker_controlled: true`.**

    3. **Assumption Properties**: Convert each trust assumption into a formal property. Example: if an assumption is "only authenticated Engine API callers can trigger newPayload," the property would be `forall caller: engineAPI.newPayload(caller, payload) => caller.hasValidJWT == true`.

    4. **Invariant Properties**: Ensure every invariant identified in the subgraphs (from `.mmd` `note` blocks with `INV-NNN:` labels) is represented as a formal property.

    5. **State Transition Properties**: For critical state transitions, define precise pre-conditions that must be met before the transition and post-conditions that must be true after.

    6. **Classify Reachability**: For each property, determine:
       - `entry_points`: List of entry points that can trigger this property (e.g., `["P2P", "EngineAPI"]`)
       - `attacker_controlled`: Can an external attacker control the inputs? (`true`/`false`)
       - `classification`: One of:
         - `external-reachable`: Reachable via in-scope external entry points
         - `internal-only`: Only reachable via internal calls
         - `api-only`: Only reachable via out-of-scope APIs (JSON-RPC, Beacon API)

    7. **Determine Bug Bounty Scope**: Based on reachability analysis:
       - `in-scope`: Property is reachable via in-scope entry points with attacker-controlled input
       - `out-of-scope`: Property is only reachable via out-of-scope entry points
       - `conditional`: Requires specific conditions or further investigation

    8. **Assign Severity**: Use the `severity_classification` from `bug_bounty_scope` as the **sole decision boundary**. For each property:
       - Ask: **"If this property is violated, what is the blast radius on the live network?"**
       - Start from INFORMATIONAL and escalate **only** when the violation's impact meets or exceeds the next level's `impact` threshold.
       - A correctness property (data format, type constraint, encoding rule) is INFORMATIONAL unless you can articulate a concrete attack path where violating it causes network-level impact (crashes, splits, slashing at the threshold %).
       - Do NOT inflate severity based on "importance to correctness" — severity is about **attacker-exploitable network impact**, not code criticality.

    9. **Determine Bug Bounty Eligibility**: A property is `bug_bounty_eligible: true` if:
       - `reachability.classification == "external-reachable"` AND
       - `reachability.bug_bounty_scope == "in-scope"` AND
       - `severity` is `MEDIUM` or higher

    10. **Assign IDs**: Assign a unique ID per property using the `_id_prefix` from the context data:
        - Use the `_id_prefix` field from the input context (e.g., `"PROP-txval"`)
        - Format: `{_id_prefix}-{type_abbrev}-{seq:03d}`
          - `type_abbrev`: `inv` (invariant), `pre` (pre-condition), `post` (post-condition), `asm` (assumption)
          - `seq`: 1-based sequence within this (prefix, type) combination
        - Example: `PROP-txval-inv-001`, `PROP-p2p-pre-003`
        - Fallback: If `_id_prefix` is not available, use `PROP-{hash8}-{type_abbrev}-{seq:03d}` where `hash8` is the first 8 chars of a hash of the source file path
  </phase_b>

  <severity_context>
    The `severity_classification` object inside `bug_bounty_scope` is the **sole decision boundary** for severity assignment.
    - Each level's `impact` field defines the minimum blast radius required. Severity is about **attacker-exploitable network impact**, not code criticality or "importance."
    - A property that enforces a data format constraint (e.g., fixed-length fields, type bounds) is INFORMATIONAL unless violating it leads to a concrete attack path with measurable network impact at the level's threshold.
    - If no `severity_classification` is present, default all properties to MEDIUM and flag for manual review.
  </severity_context>

  <output_schema>
    For each item processed, produce a result object. **Keep properties compact** — downstream phases only need the fields shown below.
    ```json
    {
      "properties": [
        {
          "property_id": "PROP-txval-inv-001",
          "text": "Total supply must not change during transfer.",
          "type": "invariant",
          "assertion": "forall transfer(from, to, amt): supply_before == supply_after",
          "severity": "CRITICAL",
          "covers": "FN-001",
          "reachability": {
            "classification": "external-reachable",
            "entry_points": ["P2P", "Transaction"],
            "attacker_controlled": true,
            "bug_bounty_scope": "in-scope"
          },
          "exploitability": "external-attack",
          "bug_bounty_eligible": true
        }
      ],
      "metadata": {
        "timestamp": "...",
        "total_properties": 50,
        "by_severity": { "CRITICAL": 5, "HIGH": 12, "MEDIUM": 18, "LOW": 10, "INFORMATIONAL": 5 },
        "by_scope": { "in_scope": 35, "out_of_scope": 10, "conditional": 5 },
        "bug_bounty_eligible_count": 30
      }
    }
    ```

    **Field size rules:**
    - `text`: max 120 characters. One sentence, no preamble.
    - `assertion`: max 200 characters. Formal expression only.
    - `covers`: **string** — the primary element ID only (e.g., `"FN-001"`). NOT an object.
    - `reachability`: **4 fields only** — `classification`, `entry_points`, `attacker_controlled`, `bug_bounty_scope`. No `validation_layers`, `notes`, or other fields.
    - `entry_points`: max 3 items.
    - Do NOT include `severity_justification`, `bug_bounty_notes`, `source_assumption_id`, `source_invariant_id`, `source_threat_id`, `trust_model_summary`, or `source_files` in the output.
  </output_schema>

  <quality_checklist>
    **Before writing output, verify:**
    - [ ] Trust model analysis completed: actors, boundaries, assumptions, Ethereum-specific STRIDE
    - [ ] STRIDE threat properties generated first — each STRIDE category that produced threats in Phase A has at least one property
    - [ ] All properties have `reachability` with exactly 4 fields: `classification`, `entry_points`, `attacker_controlled`, `bug_bounty_scope`
    - [ ] All properties have `severity` (one of: CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL)
    - [ ] Severity assigned using `severity_classification.impact` thresholds, not intuitive importance — correctness-only properties without concrete network impact are INFORMATIONAL
    - [ ] All properties have `exploitability` classification
    - [ ] All properties have `bug_bounty_eligible` determination
    - [ ] `covers` is a string (primary element ID), not an object
    - [ ] `text` is ≤ 120 chars, `assertion` is ≤ 200 chars
    - [ ] Properties are prioritized by `bug_bounty_scope` (in-scope first)
    - [ ] IDs follow the `{_id_prefix}-{type_abbrev}-{seq:03d}` format
    - [ ] `metadata.total_properties` == actual length of `properties` array, `sum(by_severity.values()) == total_properties`
  </quality_checklist>

  <data_sources>
    - **Queue File**: Contains `item_ids` and `context_file` path. Read the context file to get item data keyed by ID, each with `subgraph_files` paths and required `bug_bounty_scope` inline JSON.
    - **Subgraph Files**: 01b PARTIAL JSONs containing `.mmd` file paths and subgraph data.
  </data_sources>
</task>

<output>
  <format>JSON object with "properties" key (NOT a JSON array)</format>
  <stdout>Max 8 lines: batch size, items processed, short status.</stdout>
  <final_line>Output File: {{OUTPUT_FILE}}</final_line>
</output>
