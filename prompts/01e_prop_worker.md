
---
Description: [PARALLEL WORKER] Generate security properties for subgraph files. Create formal properties covering nodes, edges, and trust boundaries.
Usage: `/01e_prop_worker WORKER_ID=... QUEUE_FILE=...`
Example: `/01e_prop_worker WORKER_ID=0 QUEUE_FILE=outputs/01e_QUEUE_0.json`
Language: English only.
Execution hint: This is a worker prompt for parallel execution. Called by run_worker.py.
---

# **Security Property Generation (Parallel Worker)**

**Goal**
Process subgraph files from your assigned worker queue. For each subgraph, generate comprehensive security properties covering all nodes and edges.

## Worker Configuration

- **`WORKER_ID`**: The numeric ID of this worker (0, 1, 2, ...)
- **`QUEUE_FILE`**: Path to this worker's queue file (e.g., `outputs/01e_QUEUE_0.json`)

**Additional Input:** Trust model partials from `outputs/01d_TRUSTMODEL_PARTIAL_*.json`

**Output:** `outputs/01e_PROP_PARTIAL_W{WORKER_ID}_{N}.json`

---

## 1) Inputs

1. **Worker Queue File:** The file specified by `QUEUE_FILE`
   - Contains `items`: list of subgraph file paths assigned to this worker
   - Contains `processed`: list of already processed file paths

2. **Trust Model Partials:** `outputs/01d_TRUSTMODEL_PARTIAL_*.json`
   - Used to identify boundary edges and trust levels

---

## 2) Worker Execution Logic

### **Task 2.1: Read Worker Queue**

1. Read the worker queue file `QUEUE_FILE`
2. Get remaining files to process
3. If no remaining files, terminate successfully

### **Task 2.2: Load Trust Model Data**

1. Read only `outputs/01d_TRUSTMODEL_PARTIAL_*.json` files whose `metadata.source_files` include any of the batch `source_files`
2. Collect all `boundary_edges` into a lookup map by `edge_id`
3. Collect all `trusted_external_entities` by ID

### **Task 2.3: Process a Batch of Subgraph Files**

Take the **first 10 unprocessed files** from your queue (or fewer if less remain).

**For EACH subgraph file in the batch:**

#### **2.3.1: Generate Properties by Priority**

**Priority 1: Boundary Edge Properties (Input Validation)**

For each edge that is a trust boundary (found in trust model):
- Property Type: `Pre-condition`
- Focus: Validate incoming data fields
- Generate 2-3 properties per boundary edge

Example properties:
- Format validation: "Field X must be valid type Y"
- Range validation: "Value must be within bounds"
- Cryptographic: "Signature must be valid"

**Priority 2: Ambiguity & Assumption Properties**

For each `ambiguity` and `implicit_assumption` in the subgraph:
- Property Type: `Invariant` or `Pre-condition`
- Focus: Formalize the assumption

**Priority 3: State Transition Properties**

For internal edges (Action → State):
- Property Type: `Post-condition`
- Focus: Define correct state after action

**Priority 4: General Invariants**

For important states:
- Property Type: `Invariant`
- Focus: System-wide safety rules

#### **2.3.2: Property Format**

Each property must include:
- `id`: Unique ID (e.g., `PROP-W{WORKER_ID}-{SUBGRAPH}-{TYPE}-{N}`)
- `type`: One of `Pre-condition`, `Post-condition`, `Invariant`
- `natural_language`: Human-readable statement
- `covers`: Object with:
  - `nodes`: List of covered node IDs
  - `edges`: List of covered edge IDs
  - `is_boundary_edge`: true if covers a boundary edge
  - `primary_element`: The main element this property addresses
- `related_ambiguity_id`: If derived from an ambiguity
- `related_assumption_id`: If derived from an assumption

#### **2.3.3: Coverage Tracking**

Track which nodes and edges are covered by properties.
Report coverage in metadata.

### **Task 2.4: Write Outputs**

1. **Generate Partial Properties:**
   - Create `outputs/01e_PROP_PARTIAL_W{WORKER_ID}_{BATCH}.json`
   - Ensure `metadata.source_files` lists **all files in this 10-item batch**

2. **Update Worker Queue:**
   - Add processed files to `processed` array
   - Overwrite `QUEUE_FILE`

---

## 3) Required Output Format (JSON)

**Partial Properties:** `outputs/01e_PROP_PARTIAL_W{WORKER_ID}_{BATCH}.json`

```json
{
  "metadata": {
    "worker_id": 0,
    "batch": 1,
    "generated_at": "2024-01-26T12:00:00Z",
    "source_files": [
      "outputs/01b_SUBGRAPHS/spec_abc123.json"
    ],
    "total_properties": 15
  },
  "properties": [
    {
      "id": "PROP-W0-EIP4844-PRECOND-001",
      "type": "Pre-condition",
      "natural_language": "The blob transaction gas limit must be greater than the intrinsic gas cost.",
      "covers": {
        "nodes": ["STATE-BLOB-TX-RECEIVED"],
        "edges": ["EDGE-USER-SUBMIT-BLOB-TX"],
        "is_boundary_edge": true,
        "primary_element": "EDGE-USER-SUBMIT-BLOB-TX"
      },
      "related_ambiguity_id": null,
      "related_assumption_id": null
    },
    {
      "id": "PROP-W0-EIP4844-POSTCOND-001",
      "type": "Post-condition",
      "natural_language": "After blob validation completes, the blob commitment must be stored in the beacon state.",
      "covers": {
        "nodes": ["STATE-BLOB-COMMITMENT-VALID", "ACTION-VALIDATE-KZG-COMMITMENT"],
        "edges": ["EDGE-KZG-VALID"],
        "is_boundary_edge": false,
        "primary_element": "ACTION-VALIDATE-KZG-COMMITMENT"
      },
      "related_ambiguity_id": null,
      "related_assumption_id": "ASSUM-EIP4844-01"
    }
  ],
  "coverage_summary": {
    "total_nodes_in_source": 10,
    "total_edges_in_source": 8,
    "nodes_covered": 10,
    "edges_covered": 8,
    "coverage_percentage": 100.0
  }
}
```

**Updated Worker Queue:** `QUEUE_FILE`
```json
{
  "worker_id": 0,
  "phase": "01e",
  "items": ["outputs/01b_SUBGRAPHS/spec_abc.json", "..."],
  "processed": ["outputs/01b_SUBGRAPHS/spec_abc.json"],
  "total_items": 25
}
```

---

## 4) Quality Checklist

- [ ] All boundary edges have properties (highest priority)
- [ ] All ambiguities have corresponding properties
- [ ] All assumptions have corresponding properties
- [ ] Internal state transitions have post-conditions
- [ ] Coverage tracking is accurate
- [ ] Property IDs are unique
