
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
    You are a **Formal Methods Specialist** and **Security Architect** with deep expertise in the target system's architecture and attack surface. You think adversarially, question every interaction, and translate high-level security requirements into precise, machine-verifiable formal properties. You think in terms of invariants, pre-conditions, and post-conditions. **You are also a Bug Bounty Triager who understands the importance of prioritizing findings by their exploitability and scope.**
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

    1. **Identify Actors**: From subgraph descriptions, node types, function names, and edge actions, identify all actors that interact with the system. Do NOT search the codebase — derive everything from subgraphs + bug_bounty_scope only. Actors include any entity that sends, receives, or transforms data: network peers, API clients, internal components, administrators, external services, databases, file system, etc.

    2. **Map Trust Boundaries**: Determine the boundaries between actors. A trust boundary exists wherever data or control passes from one actor to another with a different level of trust. **For each boundary, derive from subgraph structure:**
       - `entry_point_type`: How is this boundary reached? (e.g., `Network`, `HTTP/gRPC`, `IPC/API`, `CLI`, `FileSystem`, `MessageQueue`, `Internal`)
       - `bug_bounty_scope`: Is this boundary in-scope? (`in-scope`, `out-of-scope`, `conditional`)
       - `attacker_controlled`: Can an external attacker control data crossing this boundary? (`true`, `false`)

    3. **Document Assumptions**: For each boundary, explicitly state the trust assumptions. For example: "We trust that the authentication layer rejects unauthenticated callers," "Remote peers can send arbitrary data — all input must be validated," "The database returns well-formed records."

    4. **Apply STRIDE Threat Model**: For each identified trust boundary and interaction, systematically analyze potential threats. Think from first principles about how each boundary can be abused. Use the categories below as a thinking framework — adapt the questions to the specific domain of the target system.

       - **Spoofing (Identity / Authentication)**:
         - Can an unauthenticated actor forge identity credentials, session tokens, or discovery records?
         - Can an attacker impersonate an authorized actor by forging or reusing credentials?
         - Can inter-component API callers bypass authentication (e.g., missing auth check, default credentials)?
         - Can an attacker replay authenticated messages from a different context, version, or session?

       - **Tampering (Data Integrity)**:
         - Can network messages or API payloads be modified in transit or at rest without detection?
         - Can an attacker manipulate authoritative data structures (databases, state stores, configuration)?
         - Can service discovery, routing tables, or DNS records be poisoned to redirect traffic?
         - Can data integrity proofs, checksums, or cryptographic commitments be corrupted without detection?
         - Can an attacker tamper with consensus or decision state (accepted results, finalized records, leader election)?
         - Can path traversal (CWE-22) allow reading or writing files outside the intended directory?
         - Can an attacker inject commands, queries, or code through unsanitized input (CWE-78/89/94)?

       - **Repudiation (Audit / Accountability Evasion)**:
         - Can a participant commit a protocol or policy violation that evades the system's detection mechanism?
         - Can an attacker cause the system to produce contradictory or conflicting outputs?
         - Can violation evidence or audit logs be suppressed, truncated, or discarded before processing?
         - Can a privileged actor selectively exclude, reorder, or tamper with audit records?

       - **Information Disclosure (Confidentiality / Leaks)**:
         - Can pending or queued data leak to enable front-running or ordering manipulation?
         - Can timing or size side channels reveal secret material or upcoming privileged actions?
         - Can participant rosters, role assignments, or internal topology be exfiltrated to enable targeted attacks?
         - Can pre-images of cryptographic commitments be obtained before the intended reveal time?
         - Can error messages, stack traces, or debug output expose internal state to untrusted actors (CWE-200)?
         - Can sensitive data (keys, tokens, PII) remain in memory, logs, or temp files after use?

       - **Denial of Service (Availability / Resource Exhaustion)**:
         - Can message flooding or payload spam exhaust memory, CPU, disk I/O, or file descriptors?
         - Can network partitioning or eclipse attacks isolate the node from legitimate peers?
         - Can a slow client, slow loris connection, or incomplete request starve the worker/connection pool?
         - Can malformed serialized payloads cause excessive deserialization, parsing, or regex backtracking cost?
         - Can malformed, truncated, or structurally invalid input cause an unhandled exception (index-out-of-bounds, null dereference, assertion failure, stack overflow) that crashes the process? For every deserialization or parsing entry point reachable from untrusted sources, the system must reject invalid input gracefully without terminating. This is distinct from resource exhaustion — even an O(1) crash is a critical DoS vector.
         - Can an attacker trigger excessive recomputation of derived state (re-indexing, cache rebuilding, state replays)?
         - Can pub/sub, broadcast, or fan-out mechanisms be manipulated to cause message amplification?
         - Can an externally-supplied numeric value control a loop bound or allocation size without an upper-bound check? If the domain of valid values is smaller than the type's range, an attacker can force unbounded iteration or memory allocation (CWE-770).
         - Can the same mutable external state be read multiple times within one call without caching the first result? If so, an attacker who changes the state between reads can cause the function to operate on inconsistent snapshots (TOCTOU across repeated reads).
         - Can an attacker cause deadlock or livelock by acquiring resources in an unexpected order?

       - **Elevation of Privilege (Authorization / Access Control)**:
         - Can an attacker escalate from an unprivileged role to an administrative or system role?
         - Can a user-controlled key or identifier be used to access another user's resources (CWE-639)?
         - Can an attacker manipulate voting, ranking, or selection weights to gain disproportionate influence?
         - Can timing manipulation allow a participant to claim resources or actions outside their permitted window?
         - Can input grinding allow an attacker to influence randomized role assignments or selections?
         - Can unauthorized actions be performed through internal or inter-component APIs missing authorization checks (CWE-862)?
         - Can deserialization of untrusted data lead to arbitrary object creation or code execution (CWE-502)?
  </phase_a>

  <phase_b title="Property Generation">
    Using the trust model from Phase A, generate formal properties. Work through each source below in order — do not skip any.

    1. **STRIDE Threat Properties** (from Phase A step 4): For each concrete threat identified in the Ethereum-specific STRIDE analysis, create a property that, if verified, would mitigate that threat. Each of the 6 STRIDE categories that produced threats in Phase A must yield at least one property. If a category produced no relevant threats for this subgraph, skip it — do not force irrelevant properties.

    2. **Trust Boundary Properties**: For each trust boundary identified in Phase A, formulate properties that must hold true for the boundary to be secure. **Prioritize boundaries marked as `in-scope` and `attacker_controlled: true`.**

    3. **Assumption Properties**: Convert each trust assumption into a formal property. Example: if an assumption is "only authenticated callers can invoke a critical operation," the property would be `forall caller: critical_op(caller, payload) => caller.is_authenticated == true`.

    4. **Invariant Properties**: Ensure every invariant identified in the subgraphs (from `.mmd` `note` blocks with `INV-NNN:` labels) is represented as a formal property. Additionally:
       - When the specification defines a data structure with ordering, uniqueness, or completeness constraints, consider that implementations may construct the same structure via multiple code paths (config loaders, constructors, deserializers). Generate an invariant asserting that the constraint holds regardless of which construction path is taken.
       - **[CRITICAL — commonly missed]** When the specification describes a data structure with both declared metadata (counts, lengths, hashes) and actual data arrays, you MUST generate an invariant asserting their consistency. Specifically:
         - Every structure where a count/list of identifiers is declared separately from the actual data MUST have: `len(declared) == len(actual)` (e.g., `len(tx.hashes) == len(wrapper.data_items)`, `len(header.field_count) == len(body.fields)`).
         - Each pair of parallel arrays that are iterated together MUST have a length equality property. If code iterates one array using the other's length as the loop bound, a mismatch causes index-out-of-bounds crashes or silent data truncation.
         - This applies to wrapper/envelope patterns where an outer object declares identifiers (hashes, keys, counts) and an inner object or sidecar carries the actual data.

    5. **State Transition Properties**: For critical state transitions, define precise pre-conditions that must be met before the transition and post-conditions that must be true after. Pay special attention to **lifecycle events** (fork transitions, epoch boundaries, validator set changes): any derived or cached state that depends on the pre-transition configuration must be invalidated or refreshed before post-transition operations that consume it.

    6. **Optimization Correctness Properties**: When the specification describes an operation whose correctness is critical (verification, validation, proof checking, uniqueness enforcement), consider that implementations commonly cache, deduplicate, or precompute results for performance. For each such operation, generate a property asserting that any such optimization must preserve the original correctness guarantee — i.e., the optimized path must produce the same accept/reject decision as the unoptimized path for all inputs. Mark these as `type: "invariant"`, severity based on blast radius if violated.

    7. **Classify Reachability**: For each property, determine:
       - `entry_points`: List of entry points that can trigger this property (e.g., `["P2P", "EngineAPI"]`)
       - `attacker_controlled`: Can an external attacker control the inputs? (`true`/`false`)
       - `classification`: One of:
         - `external-reachable`: Reachable via in-scope external entry points
         - `internal-only`: Only reachable via internal calls
         - `api-only`: Only reachable via out-of-scope APIs (JSON-RPC, Beacon API)

    8. **Determine Bug Bounty Scope**: Based on reachability analysis:
       - `in-scope`: Property is reachable via in-scope entry points with attacker-controlled input
       - `out-of-scope`: Property is only reachable via out-of-scope entry points
       - `conditional`: Requires specific conditions or further investigation

    9. **Assign Severity**: Use the `severity_classification` from `bug_bounty_scope` as the **sole decision boundary**. For each property:
       - Ask: **"If this property is violated, what is the blast radius on production systems?"**
       - Start from INFORMATIONAL and escalate **only** when the violation's impact meets or exceeds the next level's `impact` threshold.
       - A correctness property (data format, type constraint, encoding rule) is INFORMATIONAL unless you can articulate a concrete attack path where violating it causes user-facing or system-level impact (data loss, service outage, privilege escalation, etc.).
       - Do NOT inflate severity based on "importance to correctness" — severity is about **attacker-exploitable impact**, not code criticality.

    10. **Determine Bug Bounty Eligibility**: A property is `bug_bounty_eligible: true` if:
       - `reachability.classification == "external-reachable"` AND
       - `reachability.bug_bounty_scope == "in-scope"` AND
       - `severity` is `MEDIUM` or higher

    11. **Assign IDs** (**CRITICAL — every property MUST have a `property_id`**):
        - Read the `_id_prefix` field from the input context (e.g., `"PROP-txval"`)
        - Format: `{_id_prefix}-{type_abbrev}-{seq:03d}`
          - `type_abbrev`: `inv` (invariant), `pre` (pre-condition), `post` (post-condition), `asm` (assumption)
          - `seq`: 1-based sequence within this (prefix, type) combination
        - Example: `PROP-txval-inv-001`, `PROP-p2p-pre-003`
        - Fallback: If `_id_prefix` is not available, use `PROP-{hash8}-{type_abbrev}-{seq:03d}` where `hash8` is the first 8 chars of a hash of the source file path
        - **Every property in the output JSON MUST include a `"property_id"` field. Properties without IDs will be dropped by downstream phases.**
  </phase_b>

  <severity_context>
    The `severity_classification` object inside `bug_bounty_scope` is the **sole decision boundary** for severity assignment.
    - Each level's `impact` field defines the minimum blast radius required. Severity is about **attacker-exploitable network impact**, not code criticality or "importance."
    - A property that enforces a data format constraint (e.g., fixed-length fields, type bounds) is INFORMATIONAL unless violating it leads to a concrete attack path with measurable impact at the level's threshold.
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
    - [ ] Trust model analysis completed: actors, boundaries, assumptions, STRIDE threat model
    - [ ] STRIDE threat properties generated first — each STRIDE category that produced threats in Phase A has at least one property
    - [ ] All properties have `reachability` with exactly 4 fields: `classification`, `entry_points`, `attacker_controlled`, `bug_bounty_scope`
    - [ ] All properties have `severity` (one of: CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL)
    - [ ] Severity assigned using `severity_classification.impact` thresholds, not intuitive importance — correctness-only properties without concrete exploitable impact are INFORMATIONAL
    - [ ] All properties have `exploitability` classification
    - [ ] All properties have `bug_bounty_eligible` determination
    - [ ] `covers` is a string (primary element ID), not an object
    - [ ] `text` is ≤ 120 chars, `assertion` is ≤ 200 chars
    - [ ] Properties are prioritized by `bug_bounty_scope` (in-scope first)
    - [ ] **Every property has a `property_id` field** — IDs follow the `{_id_prefix}-{type_abbrev}-{seq:03d}` format
    - [ ] `metadata.total_properties` == actual length of `properties` array, `sum(by_severity.values()) == total_properties`
    - [ ] **Crash safety**: For each deserialization/parsing path from untrusted sources, at least one property asserts graceful rejection of malformed input (not just resource bounds)
    - [ ] **Declared-vs-actual consistency**: For each data structure with declared metadata (counts, hashes, keys) and separate actual data arrays, a `len(declared) == len(actual)` invariant exists
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
