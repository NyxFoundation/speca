
---
Description: [PARALLEL WORKER] Generate checklist items for trust boundary properties from property partial files.
Usage: `/02a_checklist_worker WORKER_ID=... QUEUE_FILE=...`
Example: `/02a_checklist_worker WORKER_ID=0 QUEUE_FILE=outputs/02a_QUEUE_0.json`
Language: English only.
Execution hint: This is a worker prompt for parallel execution. Called by run_worker.py.
---

# **Checklist Generation - Trust Boundaries (Parallel Worker)**

**Mindset: You are a seasoned security engineer, a "Boundary Guard", responsible for securing the perimeter of a critical system. Your primary goal is to validate every piece of data crossing the trust boundary.**

**Goal**
Process property partial files from your assigned worker queue. For each file, extract boundary properties (where `is_boundary_edge == true`) and generate high-priority audit checklist items.

## Worker Configuration

- **`WORKER_ID`**: The numeric ID of this worker (0, 1, 2, ...)
- **`QUEUE_FILE`**: Path to this worker's queue file (e.g., `outputs/02a_QUEUE_0.json`)

**Additional Input:** Trust model partials from `outputs/01d_TRUSTMODEL_PARTIAL_*.json`

**Output:** `outputs/02a_CHECKLIST_PARTIAL_W{WORKER_ID}_{N}.json`

---

## 1) Inputs

1. **Worker Queue File:** The file specified by `QUEUE_FILE`
   - Contains `items`: list of property partial file paths assigned to this worker
   - Contains `processed`: list of already processed file paths

2. **Trust Model Partials:** `outputs/01d_TRUSTMODEL_PARTIAL_*.json`
   - Used for trust level context on boundary edges, plus `target_component` and `target_component_interface` for precise boundary checks

---

## 2) Worker Execution Logic

### **Task 2.1: Read Worker Queue**

1. Read the worker queue file `QUEUE_FILE`
2. Get remaining files to process
3. If no remaining files, terminate successfully

### **Task 2.2: Load Contextual Data**

1. Read all `outputs/01d_TRUSTMODEL_PARTIAL_*.json` files
2. Collect all `boundary_edges` into a lookup map
3. Collect all `trusted_external_entities` by ID
4. For each property being processed, extract the associated trust model `audit_scope` (e.g., `CL`, `EL`) and `archetypal_attack_vectors`

### **Task 2.3: Process a Batch of Property Files**

Take the **first 5 unprocessed files** from your queue (or fewer if less remain).

**For EACH property partial file in the batch:**

#### **2.3.1: Extract Boundary Properties**

1. Read the property partial file
2. Filter to properties where `covers.is_boundary_edge == true`
3. These are the highest priority properties

#### **2.3.2: Generate Checklist Items for Each Boundary Property**

For each boundary property:

**Task A: Adopt the Right Mindset**
- If `audit_scope` is `Consensus Layer (CL)`: prioritize protocol stability and consensus integrity. Think about malicious validators, network partitions, and invalid attestations. Use `archetypal_attack_vectors` to guide what to check.
- If `audit_scope` is `Execution Layer (EL)`: prioritize state integrity and user asset safety. Think about malformed transactions, re-entrancy, and gas-related attacks.

**Task B: Generate Context-Aware Checklist Items**
- `title`: Must reflect the audit scope (e.g., "[CL AUDIT] Verify Attestation Validation at Gossip Boundary")
- `detection_procedure`: Tailor to scope (CL: fork choice, attestation validity; EL: transaction pool logic, gas accounting)
- `risk_category`: Use scope-specific risks (CL: "Consensus Failure"; EL: "Loss of Funds")

**Task C: Generate Boundary Edge Check**
- `id`: `CHECK-W{WORKER_ID}-{PROP_ID}-BOUNDARY`
- `title`: "Verify Trust Boundary Integrity for {EDGE_ID} ({TARGET_COMPONENT}: {ENTRY_POINT})"
- `severity_hint`: Almost always `Critical`
- Focus: Data validation, authentication, transport security, at the specific entry point

**Task D: Generate Associated Node Checks**
- For Action/State nodes in `covers.nodes`
- Focus: How they support boundary security

#### **2.3.3: Checklist Item Format**

Each checklist item must include:
- `id`: Unique identifier
- `property_id`: Source property ID
- `graph_element_under_test`: Node or Edge ID being audited
- `title`: Clear, actionable title
- `bug_class`: Type (Input Validation, Access Control, etc.)
- `risk_category`: Security impact area
- `severity_hint`: Critical, High, Medium, Low
- `detection_procedure`: Step-by-step audit guide
- `executable_checks`: Machine-runnable verification steps
- `notes`: **MUST** include traceability:
  `"Traceability: Property {property_id} → Edge {edge_id} ({target_component}: {target_component_interface}). This check verifies..."`

### **Task 2.4: Write Outputs**

1. **Generate Partial Checklist:**
   - Create `outputs/02a_CHECKLIST_PARTIAL_W{WORKER_ID}_{BATCH}.json`

2. **Update Worker Queue:**
   - Add processed files to `processed` array
   - Overwrite `QUEUE_FILE`

---

## 3) Required Output Format (JSON)

**Partial Checklist:** `outputs/02a_CHECKLIST_PARTIAL_W{WORKER_ID}_{BATCH}.json`

```json
{
  "metadata": {
    "worker_id": 0,
    "batch": 1,
    "generated_at": "2024-01-26T12:00:00Z",
    "stage": "02a_boundaries",
    "source_files": [
      "outputs/01e_PROP_PARTIAL_W0_1.json"
    ],
    "boundary_properties_processed": [
      "PROP-W0-EIP4844-PRECOND-001",
      "PROP-W0-EIP4844-PRECOND-002"
    ],
    "boundary_edges_covered": [
      "EDGE-USER-SUBMIT-BLOB-TX"
    ],
    "total_checks": 3
  },
  "checklist": [
    {
      "id": "CHECK-W0-PROP-W0-EIP4844-PRECOND-001-BOUNDARY",
      "property_id": "PROP-W0-EIP4844-PRECOND-001",
      "graph_element_under_test": "EDGE-USER-SUBMIT-BLOB-TX",
      "title": "Verify Trust Boundary Integrity for EDGE-USER-SUBMIT-BLOB-TX (Execution Layer (EL): eth_sendRawTransaction RPC): Blob Transaction Input Validation",
      "bug_class": "Input Validation",
      "risk_category": "Data Integrity",
      "severity_hint": "Critical",
      "detection_procedure": "1. Identify RPC endpoint for blob transaction submission. 2. Trace input validation code path. 3. Verify all blob fields are validated: versioned_hash, blob_gas, max_fee_per_blob_gas. 4. Check for proper error handling on invalid input.",
      "executable_checks": [
        {
          "tool": "grep",
          "command": "grep -r 'BlobTx' --include='*.go'",
          "assertion": "Find blob transaction handling entry points"
        },
        {
          "tool": "manual",
          "command": "Review validation logic",
          "assertion": "All blob-specific fields are validated before processing"
        }
      ],
      "notes": "Traceability: Property PROP-W0-EIP4844-PRECOND-001 → Edge EDGE-USER-SUBMIT-BLOB-TX (Execution Layer (EL): eth_sendRawTransaction RPC). This check verifies the implementation of the critical trust boundary EDGE-USER-SUBMIT-BLOB-TX, ensuring blob transactions are validated before entering the system."
    },
    {
      "id": "CHECK-W0-PROP-W0-EIP4844-PRECOND-001-ACTION",
      "property_id": "PROP-W0-EIP4844-PRECOND-001",
      "graph_element_under_test": "ACTION-VALIDATE-BLOB-TX",
      "title": "Verify ACTION-VALIDATE-BLOB-TX Correctly Enforces Blob Format Validation",
      "bug_class": "Input Validation",
      "risk_category": "Data Integrity",
      "severity_hint": "High",
      "detection_procedure": "1. Locate blob validation function. 2. Verify KZG commitment validation. 3. Check blob size limits. 4. Verify versioned hash computation.",
      "executable_checks": [
        {
          "tool": "grep",
          "command": "grep -r 'validateBlob' --include='*.go'",
          "assertion": "Find blob validation implementation"
        }
      ],
      "notes": "Traceability: Property PROP-W0-EIP4844-PRECOND-001 → Action ACTION-VALIDATE-BLOB-TX. This action supports the security of the trust boundary by validating blob data format."
    }
  ]
}
```

**Updated Worker Queue:** `QUEUE_FILE`
```json
{
  "worker_id": 0,
  "phase": "02a",
  "items": ["outputs/01e_PROP_PARTIAL_W0_1.json", "..."],
  "processed": ["outputs/01e_PROP_PARTIAL_W0_1.json"],
  "total_items": 10
}
```

---

## 4) Quality Checklist

- [ ] All boundary properties have checklist items
- [ ] Each boundary edge has a dedicated check
- [ ] Severity is appropriately set (boundaries are Critical)
- [ ] Detection procedures are actionable
- [ ] Traceability notes are complete
- [ ] Property IDs and edge IDs are accurate
