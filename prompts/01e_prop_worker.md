
---
Description: [PARALLEL WORKER] Generate security properties for subgraph files. Create formal properties covering nodes, edges, and trust boundaries.
Usage: `/01e_prop_worker WORKER_ID=... QUEUE_FILE=... [BATCH_SIZE=...]`
Example: `/01e_prop_worker WORKER_ID=0 QUEUE_FILE=outputs/01e_QUEUE_0.json BATCH_SIZE=5`
Language: English only.
Execution hint: This is a worker prompt for parallel execution. Called by run_worker.py.
---

# **Security Property Generation (Parallel Worker)**

**Goal**
Process subgraph files from your assigned worker queue. For each subgraph, generate comprehensive security properties covering all nodes and edges.

## Worker Configuration

- **`WORKER_ID`**: The numeric ID of this worker (0, 1, 2, ...)
- **`QUEUE_FILE`**: Path to this worker's queue file (e.g., `outputs/01e_QUEUE_0.json`)
- **`BATCH_SIZE` (optional)**: Max number of files to process this iteration (set dynamically by `run_worker.py`)

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

### **Task 2.3: Process a Batch of Subgraph Files (Dynamic Batching)**

Take unprocessed files from your queue **until the cumulative size reaches ~160KB** (approximately 40,000 tokens), or fewer if less remain.

**Token Estimation**:
- Estimate each subgraph file's token count as: `file_size_bytes / 4`
- Keep a running total as you add files to the batch
- Stop adding files when: `cumulative_tokens + next_file_tokens > 40,000`

**Batching Logic**:
1. Start with an empty batch
2. For each unprocessed file in the queue (in order):
   - Check the file size
   - If `cumulative_size + file_size <= 160KB`, add to batch
   - Otherwise, stop and process the current batch
3. If the batch is empty (first file > 160KB), process that single file alone

**If `BATCH_SIZE` is provided**: Use it as the max number of files to process this iteration, and still ensure you only take files from the front of the remaining queue.

**For EACH subgraph file in the batch:**

#### **2.3.1: Provide Scaffolding for Your Thought Process**

**DO NOT read the subgraph file yet.** First, answer the following scaffolding questions to establish a robust thinking framework. Your answers should be abstract and based on general systems knowledge.

**Question 1 (Verification Condition Mindset):**
"Consider a generic blockchain protocol. If this system is to be considered secure and correct, what are 3-5 fundamental conditions that MUST ALWAYS be true, regardless of the specific operations? (e.g., total supply of a token should not change, a slashed validator can never be un-slashed)."

**Question 2 (Forward Reasoning - Strongest Postcondition):**
"Imagine a function that processes a new block. Given a valid block as input, what is the STRONGEST, most specific guarantee you can make about the system's state immediately after the function completes successfully?"

**Question 3 (Backward Reasoning - Weakest Precondition):**
"To guarantee that a transaction is successfully included in a block, what is the WEAKEST, most minimal set of conditions the transaction must have satisfied before it was processed?"

**Question 4 (Invariant Discovery):**
"Consider a complex, multi-step consensus process (like voting or state synchronization). What is a plausible property that remains TRUE after each and every step of the process?"

#### **2.3.2: Generate Properties by Priority**

**NOW, you may read the subgraph file.** Use your answers from 2.3.1 as a guide.

- **Map your answers**: For each abstract condition you identified in 2.3.1, find the specific functions, state variables, and logic in the subgraph that correspond to it.
- **Generate concrete properties** using this mapping:
  - Answer to **Q1** should inspire **Invariant** properties.
  - Answer to **Q2** should inspire **Post-condition** properties.
  - Answer to **Q3** should inspire **Pre-condition** properties.
  - Answer to **Q4** should inspire **Loop Invariant** or **Protocol Invariant** properties.

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

#### **2.3.3: Property Format**

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

#### **2.3.4: Coverage Tracking**

Track which nodes and edges are covered by properties.
Report coverage in metadata.

### **Task 2.4: Write Outputs**

1. **Generate Partial Properties:**
   - Create `outputs/01e_PROP_PARTIAL_W{WORKER_ID}_{BATCH}.json`
   - Ensure `metadata.source_files` lists **all files in this batch**

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
