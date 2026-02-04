
---
Description: [PARALLEL WORKER] Verify and fix subgraph files for internal consistency. Check node/edge references, ID uniqueness, and graph connectivity.
Usage: `/01c_verify_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...]`
Example: `/01c_verify_worker WORKER_ID=0 QUEUE_FILE=outputs/01c_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1`
Language: English only.
Execution hint: This is a worker prompt for parallel execution. Called by run_worker.py.
---
**Always use /serena for development tasks to keep the workflow efficient.**

# **Subgraph Verification (Parallel Worker)**

**Goal**
Process subgraph files from your assigned worker queue. For each subgraph file, verify internal consistency, fix any issues, and ensure the graph is well-formed.

## Worker Configuration

- **`WORKER_ID`**: The numeric ID of this worker (0, 1, 2, ...)
- **`QUEUE_FILE`**: Path to this worker's queue file (e.g., `outputs/01c_QUEUE_0.json`)
- **`TIMESTAMP`**: Unix timestamp for this iteration (used in output naming)
- **`ITERATION`**: The current iteration number for this worker

**Output:** Verified/fixed subgraph files (overwritten in place) plus a timestamped copy.

---

## 1) Inputs

1. **Worker Queue File:** The file specified by `QUEUE_FILE`
   - Contains `items`: list of subgraph file paths assigned to this worker
   - Contains `processed`: list of already processed file paths

---

## 2) Worker Execution Logic

### **Task 2.1: Read Worker Queue**

1. Read the worker queue file `QUEUE_FILE`
2. Get the list of `items` (all assigned file paths)
3. Get the list of `processed` (already done file paths)
4. Calculate remaining: file paths in `items` but not in `processed`
5. If no remaining files, terminate successfully

### **Task 2.2: Process a Batch of Subgraph Files**

Take the **first 10 unprocessed files** from your queue (or fewer if less than 10 remain).

**For EACH subgraph file in the batch:**

#### **2.2.1: Load and Parse**
1. Read the JSON file
2. Extract `sub_graphs` array

#### **2.2.2: Verify Each Sub-Graph**

For each sub-graph in `sub_graphs`:

**A. ID Uniqueness Check:**
- Verify all node IDs are unique within the sub-graph
- Verify all edge IDs are unique within the sub-graph
- If duplicates found: append suffix to make unique (e.g., `_dup1`)

**B. Edge Reference Check:**
- For each edge, verify `source` references a valid node ID or external entity ID
- For each edge, verify `target` references a valid node ID or external entity ID
- If invalid reference found: either fix the reference or remove the edge

**C. Node Type Validation:**
- Verify each node has a valid `type` (State, Action, Data, etc.)
- Verify node IDs follow naming convention (`STATE-*`, `ACTION-*`, etc.)

**D. External Entity Check:**
- Verify all external entities referenced in edges exist in `external_entities`
- If missing: add placeholder external entity

**E. Graph Connectivity (Basic):**
- Check that the sub-graph is not completely disconnected
- Warn if any node has no incoming or outgoing edges (orphan)

#### **2.2.3: Fix and Save**

1. Apply any necessary fixes
2. Add `verified` metadata to the file:
```json
{
  "verified": {
    "worker_id": 0,
    "timestamp": "2024-01-26T12:00:00Z",
    "issues_found": 3,
    "issues_fixed": 3
  }
}
```
3. Overwrite the original file with the verified version
4. Also write a timestamped copy to `outputs/01b_SUBGRAPHS/spec_<hash>_verified_{TIMESTAMP}_{ITERATION}.json`

### **Task 2.3: Update Worker Queue**

**DO NOT UPDATE THE QUEUE FILE.** The runner script (`run_worker.py`) will update `processed` atomically after validating your output.

---

## 3) Required Output Format

**Updated Subgraph File:** (same path, overwritten) plus timestamped copy
```json
{
  "source_url": "https://...",
  "worker_id": 0,
  "sub_graphs": [...],
  "ambiguities": [...],
  "implicit_assumptions": [...],
  "verified": {
    "worker_id": 0,
    "timestamp": "2024-01-26T12:00:00Z",
    "issues_found": 0,
    "issues_fixed": 0
  }
}
```

**Updated Worker Queue File:** `QUEUE_FILE`
```json
{
  "worker_id": 0,
  "phase": "01c",
  "total_workers": 4,
  "items": ["outputs/01b_SUBGRAPHS/spec_abc.json", "..."],
  "processed": ["outputs/01b_SUBGRAPHS/spec_abc.json"],
  "total_items": 25
}
```

---

## 4) Quality Checklist

Before finalizing each file, verify:

- [ ] All node IDs are unique
- [ ] All edge IDs are unique
- [ ] All edge sources/targets reference valid nodes or external entities
- [ ] Node types are valid
- [ ] External entities referenced in edges exist
- [ ] `verified` metadata is added
