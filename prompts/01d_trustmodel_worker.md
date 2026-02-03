
---
Description: [PARALLEL WORKER] Generate trust model for subgraph files. Assign trust levels to external entities and identify trust boundary edges.
Usage: `/01d_trustmodel_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...]`
Example: `/01d_trustmodel_worker WORKER_ID=0 QUEUE_FILE=outputs/01d_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1`
Language: English only.
Execution hint: This is a worker prompt for parallel execution. Called by run_worker.py.
---

# **Trust Model Generation (Parallel Worker)**

**Goal**
Process subgraph files from your assigned worker queue. For each subgraph, identify external entities, assign trust levels, and identify trust boundary edges.

## 0) Define Audit Scope (NEW)

**First, determine which primary components are being audited in this context.** Analyze the provided subgraph files. If they predominantly describe Execution Layer logic (transactions, EVM, state), include "EL". If they describe Consensus Layer logic (fork choice, attestations, beacon chain), include "CL". If both are materially present, include both.

**Based on this, define the `audit_scope` object.** This is the most critical step to contextualize the entire trust model. If both EL and CL are in scope, list both in `target_components` and provide per-component scope detail.

**Example `audit_scope` (if target is EL+CL):**
```json
"audit_scope": {
  "target_components": ["Execution Layer (EL)", "Consensus Layer (CL)"],
  "description": "This audit covers both EL and CL logic and their interfaces.",
  "components": [
    {
      "component": "Execution Layer (EL)",
      "in_scope": ["Transaction Pool", "State Transition", "Engine API handlers"],
      "out_of_scope": ["P2P networking stack"]
    },
    {
      "component": "Consensus Layer (CL)",
      "in_scope": ["Fork Choice", "Attestations", "Beacon Chain state transitions"],
      "out_of_scope": ["Execution Layer internals"]
    }
  ]
}
```

## 0.5) Define Bug Bounty Scope (NEW)

**Before analyzing the EIPs, define which components are in-scope and out-of-scope for the active Bug Bounty program.** This scope must be reflected in downstream phases, so be explicit and conservative.

**If a Bug Bounty Scope block is provided at the top of this prompt, treat it as the source of truth.**
If not, check for `outputs/BUG_BOUNTY_SCOPE.json`. If neither exists, use the default Ethereum scope below.

**When a Bug Bounty Scope block is provided, you MUST copy it into your output as `bug_bounty_scope` with all fields and values intact.**
Do not summarize, drop keys, rename fields, or replace nested structures. Preserve everything, including
`trust_assumptions`, `conditional_scope`, `severity_classification`, and any additional fields that appear.
If you need to add scope-specific rationale, add it under `bug_bounty_scope.out_of_scope_reasons` while preserving all
existing keys and values.

**In-Scope (default):**
- P2P network protocols (devp2p, Beacon P2P)
- Transaction processing and validation
- Block processing and validation
- State transition logic
- Engine API (EL-CL interface)
- Consensus logic (fork choice, attestations)

**Out-of-Scope (default):**
- JSON-RPC API (public-facing HTTP API)
- Beacon API (public-facing HTTP API)
- Configuration errors (node operator mistakes)
- CL-only attacks (requires malicious CL node)
- Tests and infrastructure
- High-effort DoS (requires sustained attack)

**Define and include a `bug_bounty_scope` object in your output.** If the current EIP or subgraph indicates a different scope, add explicit rationale in `out_of_scope_reasons` without dropping any existing fields.

**Example `bug_bounty_scope` (illustrative only; if a scope block is provided, copy it verbatim and include all fields):**
```json
"bug_bounty_scope": {
  "program_name": "Ethereum Bug Bounty",
  "program_url": "https://ethereum.org/en/bug-bounty/",
  "in_scope_components": ["P2P", "Transaction Pool", "Block Validation", "Engine API"],
  "out_of_scope_components": ["JSON-RPC API", "Beacon API", "Configuration"],
  "trust_assumptions": {
    "engine_api": "SEMI_TRUSTED",
    "local_validator": "SEMI_TRUSTED",
    "p2p_peers": "UNTRUSTED"
  },
  "conditional_scope": [
    "High-effort DoS may be out-of-scope unless a clear safety impact is shown."
  ],
  "severity_classification": {
    "critical": "Remote consensus failure or chain split",
    "high": "Funds loss or consensus safety violation",
    "medium": "Significant degradation or safety risk",
    "low": "Minor impact or misbehavior",
    "informational": "No direct security impact"
  },
  "out_of_scope_reasons": {
    "JSON-RPC API": "Explicitly out-of-scope per Ethereum Bug Bounty",
    "Beacon API": "Explicitly out-of-scope per Ethereum Bug Bounty",
    "Configuration": "Requires node operator error, not external attack"
  }
}
```

## 1) Define Archetypal Attack Vectors (NEW)

**Before analyzing the specific EIPs, first define the archetypal attack vectors for both EL and CL from a top-down perspective.** This ensures comprehensive threat modeling even if the EIPs are EL-focused.

### Task 1.1: Define EL Attack Vectors

- **Source**: Malicious User / DApp
- **Entry Point**: JSON-RPC API (e.g., `eth_sendRawTransaction`)
- **Threat**: Submit malformed transactions, resource exhaustion attacks.

- **Source**: Malicious Peer Node
- **Entry Point**: P2P Network (devp2p)
- **Threat**: Eclipse attacks, send invalid blocks/transactions.

### Task 1.2: Define CL Attack Vectors

- **Source**: Malicious Validator
- **Entry Point**: P2P Network (Beacon API / gossip)
- **Threat**: Propose invalid blocks, submit conflicting attestations (slashing condition), censorship.

- **Source**: Malicious External Service
- **Entry Point**: External APIs (e.g., MEV-Boost relay, checkpoint sync endpoint)
- **Threat**: Provide incorrect data, censorship, denial of service.

**Now, proceed to analyze the EIPs. When defining `trusted_external_entities`, you MUST consider both the bottom-up threats from the EIPs AND these top-down archetypal threats.**

## Worker Configuration

- **`WORKER_ID`**: The numeric ID of this worker (0, 1, 2, ...)
- **`QUEUE_FILE`**: Path to this worker's queue file (e.g., `outputs/01d_QUEUE_0.json`)
- **`TIMESTAMP`**: Unix timestamp for this iteration (used in output naming)
- **`ITERATION`**: The current iteration number for this worker

**Output:** `outputs/01d_TRUSTMODEL_PARTIAL_W{WORKER_ID}_{TIMESTAMP}_{ITERATION}.json`

---

## 2) Inputs

1. **Worker Queue File:** The file specified by `QUEUE_FILE`
   - Contains `items`: list of subgraph file paths assigned to this worker
   - Contains `processed`: list of already processed file paths

---

## 3) Worker Execution Logic

### **Task 3.1: Read Worker Queue**

1. Read the worker queue file `QUEUE_FILE`
2. Get the list of `items` (all assigned file paths)
3. Get the list of `processed` (already done file paths)
4. Calculate remaining: file paths in `items` but not in `processed`
5. If no remaining files, terminate successfully

### **Task 3.2: Process a Batch of Subgraph Files**

Take the **first `BATCH_SIZE` unprocessed files** from your queue (or fewer if less remain). If `BATCH_SIZE` is not provided, default to **5**.

**For EACH subgraph file in the batch:**

#### **2.2.1: Extract External Entities**

1. Read the subgraph file
2. Collect all `external_entities` from all `sub_graphs`
3. Deduplicate by ID

#### **2.2.2: Validate External Entities**

**External Entity Criteria:**
- ✅ Resides outside the system boundary
- ✅ Sends data INTO the system under audit
- ✅ Not under direct control of the system

**If misclassified (internal components), note in `misclassified_entities`.**

#### **2.2.3: Classify External Entities and Entry Points**

For each external source of data that interacts with an in-scope `target_component`, define an entity. **Do not model the `target_component` itself as an external entity.** Instead, model its interlocutors.

- **Name**: Be specific. Instead of "Consensus Layer", use "CL via Engine API". Instead of "User", use "User via JSON-RPC".
- **Trust Level**: Assign a trust level based on the entry point's characteristics.
- **Entry Point**: Describe the specific interface (e.g., "Engine API newPayloadV3", "eth_sendRawTransaction RPC").
- **Target Component**: Explicitly state which in-scope component this entity is interacting with (EL or CL).

| Trust Level | When to Use |
|-------------|-------------|
| `SEMI_TRUSTED` | Authenticated channel (e.g., Engine API with JWT), but data content requires validation. **The CL is the primary example.** |
| `UNTRUSTED` | Unauthenticated channel (e.g., P2P network, public JSON-RPC). All data is potentially malicious. **This is the default.** |

**Guidelines:**
- Default to `UNTRUSTED`
- Authentication ≠ Trust
- Never `TRUSTED` for network peers

#### **2.2.4: Identify Trust Boundary Edges**

For each external entity you defined, identify the specific edge in the graph where its data crosses into the target component it interacts with.

Create boundary edge entry:
- `edge_id`: The edge ID
- `source_entity_id`: The ID of the refined external entity (e.g., `EXT-CL-ENGINE-API`)
- `target_component`: The in-scope component receiving the data ("Execution Layer (EL)" or "Consensus Layer (CL)")
- `target_component_interface`: The specific entry point on the `target_component` (e.g., "Engine API newPayloadV3")
- `security_assumption`: State what MUST be validated at this boundary. For `SEMI_TRUSTED` entities, this focuses on content validation. For `UNTRUSTED` entities, this includes authentication, authorization, and content validation.

#### **2.2.5: Coverage Verification**

For each external entity, verify at least one boundary edge exists.
Report any coverage gaps.

### **Task 3.3: Write Outputs**

1. **Generate Partial Trust Model:**
   - Create `outputs/01d_TRUSTMODEL_PARTIAL_W{WORKER_ID}_{TIMESTAMP}_{ITERATION}.json`
   - Set `metadata.batch` to `ITERATION`

2. **Update Worker Queue:**
   - Add processed file paths to `processed` array
   - Overwrite `QUEUE_FILE`

---

## 4) Required Output Format (JSON)

**Partial Trust Model:** `outputs/01d_TRUSTMODEL_PARTIAL_W{WORKER_ID}_{TIMESTAMP}_{ITERATION}.json`

If a Bug Bounty Scope block was provided at the top of this prompt, you MUST copy it verbatim as `bug_bounty_scope` and include all fields.
Do not drop or rename keys.

```json
{
  "metadata": {
    "worker_id": 0,
    "batch": 1,
    "generated_at": "2024-01-26T12:00:00Z",
    "source_files": [
      "outputs/01b_SUBGRAPHS/spec_abc123.json",
      "outputs/01b_SUBGRAPHS/spec_def456.json"
    ]
  },
  "audit_scope": {
    "target_components": ["Execution Layer (EL)", "Consensus Layer (CL)"],
    "description": "Auditing both EL and CL and their interfaces.",
    "components": [
      {
        "component": "Execution Layer (EL)",
        "in_scope": ["Transaction Pool", "State Transition", "Engine API"],
        "out_of_scope": ["P2P networking stack"]
      },
      {
        "component": "Consensus Layer (CL)",
        "in_scope": ["Fork Choice", "Attestations", "Beacon Chain state transitions"],
        "out_of_scope": ["Execution Layer internals"]
      }
    ]
  },
  "bug_bounty_scope": {
    "program_name": "Ethereum Bug Bounty",
    "program_url": "https://ethereum.org/en/bug-bounty/",
    "in_scope_components": ["P2P", "Transaction Pool", "Block Validation", "Engine API"],
    "out_of_scope_components": ["JSON-RPC API", "Beacon API", "Configuration"],
    "trust_assumptions": {
      "engine_api": "SEMI_TRUSTED",
      "local_validator": "SEMI_TRUSTED",
      "p2p_peers": "UNTRUSTED"
    },
    "conditional_scope": [
      "High-effort DoS may be out-of-scope unless a clear safety impact is shown."
    ],
    "severity_classification": {
      "critical": "Remote consensus failure or chain split",
      "high": "Funds loss or consensus safety violation",
      "medium": "Significant degradation or safety risk",
      "low": "Minor impact or misbehavior",
      "informational": "No direct security impact"
    },
    "out_of_scope_reasons": {
      "JSON-RPC API": "Explicitly out-of-scope per Ethereum Bug Bounty",
      "Beacon API": "Explicitly out-of-scope per Ethereum Bug Bounty",
      "Configuration": "Requires node operator error, not external attack"
    }
  },
  "misclassified_entities": [
    {
      "id": "EXT-INTERNAL-SCHEDULER",
      "reason": "Internal component, not external entity"
    }
  ],
  "trusted_external_entities": [
    {
      "id": "EXT-USER-JSON-RPC",
      "name": "User via JSON-RPC",
      "trust_level": "UNTRUSTED",
      "target_component": "Execution Layer (EL)",
      "entry_point": "eth_sendRawTransaction RPC",
      "rationale": "User input via RPC, no authentication required."
    },
    {
      "id": "EXT-CL-ENGINE-API",
      "name": "Consensus Layer via Engine API",
      "trust_level": "SEMI_TRUSTED",
      "target_component": "Execution Layer (EL)",
      "entry_point": "Engine API (newPayload, forkchoiceUpdated)",
      "rationale": "Authenticated via JWT, but payload content must be validated."
    }
  ],
  "boundary_edges": [
    {
      "edge_id": "EDGE-USER-SUBMIT-TX",
      "source_entity_id": "EXT-USER-JSON-RPC",
      "target_component": "Execution Layer (EL)",
      "target_component_interface": "eth_sendRawTransaction RPC",
      "security_assumption": "Full transaction validation required."
    }
  ],
  "coverage_analysis": {
    "total_external_entities": 2,
    "entities_with_boundary_edges": 2,
    "coverage_gaps": [],
    "verification_status": "COMPLETE"
  }
}
```

**Updated Worker Queue:** `QUEUE_FILE`
```json
{
  "worker_id": 0,
  "phase": "01d",
  "items": ["outputs/01b_SUBGRAPHS/spec_abc.json", "..."],
  "processed": ["outputs/01b_SUBGRAPHS/spec_abc.json"],
  "total_items": 25
}
```

---

## 5) Quality Checklist

- [ ] All external entities are validated (truly external)
- [ ] Each entity has appropriate trust level with rationale
- [ ] All boundary edges identified
- [ ] Coverage analysis complete
- [ ] No entity without boundary edge (or documented in gaps)
