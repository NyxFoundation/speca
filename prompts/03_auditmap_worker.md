
---
Description: [UNIFIED PARALLEL WORKER] Formal static audit with three-phase formal methods (abstract interpretation, symbolic execution, invariant proving).
Usage: `/03_auditmap_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...] [BATCH_SIZE=...]`
Example: `/03_auditmap_worker WORKER_ID=0 QUEUE_FILE=outputs/03_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1 BATCH_SIZE=5`
Language: English only.
Execution hint: This is a worker prompt for parallel execution. Called by run_worker.py.
---

# Formal Auditmap

**Goal**
For each checklist item in the current batch, perform a rigorous, three-phase formal static audit to either prove the existence of a vulnerability or prove its absence, without executing code. This worker replaces the need for a separate dynamic testing phase.

---

## 1. Inputs

1.  **Worker Queue File**: `QUEUE_FILE` containing items with `check_id`, `checklist_file`, pre-resolved `checklist_item`, and optionally `subgraph_id`/`subgraph_file` (note: `subgraph_id` may be null).
2.  **Checklist Partial Files**: `outputs/02_CHECKLIST_PARTIAL_*.json` (only needed if a queue item lacks `checklist_item`).
3.  **Property File**: The `source_file` referenced in the checklist item (e.g., `outputs/01e_PROP_PARTIAL_*.json`). Loaded to get the original property assertion.
4.  **Subgraph File**: The subgraph file corresponding to the property (e.g., `outputs/01b_SUBGRAPHS/*.json`). Loaded to map the abstract graph element to concrete code.

---

## 2. Worker Configuration

- **`WORKER_ID`**: The numeric ID of this worker (0, 1, 2, ...)
- **`QUEUE_FILE`**: Path to this worker's queue file (e.g., `outputs/03_QUEUE_0.json`)
- **`TIMESTAMP`**: Unix timestamp for this iteration (used in output naming)
- **`ITERATION`**: The current iteration number for this worker
- **`BATCH_SIZE`**: Number of items to process this iteration (may be dynamic)

**Output:** `outputs/03_AUDITMAP_PARTIAL_W{WORKER_ID}_{TIMESTAMP}_{ITERATION}.json`

---

## 3. Execution Logic

### **Task 3.1: Read Queue & Resolve Checklist Items**

1.  Read `QUEUE_FILE`.
2.  Identify unprocessed items (items whose `check_id` is not in `processed`).
3.  If no items remain, terminate successfully.
4.  Take the first `BATCH_SIZE` items as `current_batch`.
5.  For each item in `current_batch`, use `item["checklist_item"]` as the full checklist JSON object.
6.  **Fallback (only if `checklist_item` is missing)**: load `item["checklist_file"]`, then search the file's `checklist` array for the object where `id == check_id`.

### **Task 3.2: Code Scope Identification**

For each checklist item in the batch:

1.  **Parse Checklist Item**: Extract `property_id` and `graph_element_under_test`.
2.  **Load Property**: Read the property file to understand the original assertion (`property.description`).
3.  **Load Subgraph**: If `subgraph_file` is present on the queue item, load it directly. Otherwise, resolve the subgraph via the property file and load it.
4.  **Map to Code**:
    - If `subgraph_id` is present, first search that subgraph’s `nodes` and `edges` for `graph_element_under_test`.
    - If `subgraph_id` is **null** (or the element is not found in that subgraph), scan the **entire file** for the ID across:
      - `sub_graphs[*].nodes`
      - `sub_graphs[*].edges`
      - top-level `ambiguities`
      - top-level `implicit_assumptions`
    - Extract the associated code metadata: `file`, `function`, `line_range`, and any other relevant details. This is your **Code Scope**.

### **Task 3.3: Three-Phase Formal Audit**

For the identified **Code Scope**, perform the following three phases sequentially. You are to adopt a different expert mindset for each phase.

#### **Phase 1: Abstract Interpretation**

*   **Mindset**: You are an **Abstract Interpretation Specialist**. Your goal is to understand the possible states of all variables without considering specific execution paths. You think in terms of ranges, sets, and potential states.

*   **Procedure**:
    1.  Identify all variables within the Code Scope.
    2.  For each variable, determine its abstract domain (e.g., integer range `[0, 256]`, a set of possible string values, a boolean `true`/`false`).
    3.  Trace how operations within the code transform these abstract domains. Do not track concrete values.
    4.  Look for potential anomalies: Can an integer overflow its range? Can a variable become null? Can a list grow unbounded?

*   **Output (Phase 1)**: A summary of the abstract state analysis, highlighting any potential state-space anomalies.

#### **Phase 2: Symbolic Execution**

*   **Mindset**: You are a **Symbolic Execution Engineer**. Your goal is to find a concrete path through the code that violates the property. You think in terms of path conditions and constraints.

*   **Procedure**:
    1.  Treat all inputs to the Code Scope as symbolic variables.
    2.  Traverse the code's control flow graph. At each branch (`if/else`), create a new path condition.
    3.  The goal is to find a set of path conditions that, when combined with the negation of the original property's assertion, are satisfiable.
    4.  Use a constraint solver mindset (e.g., Z3): Can you find concrete input values (`x=5`, `y=10`) that satisfy these conditions and trigger the bug?
    5.  If a satisfying assignment is found, you have constructed a **counterexample**.

*   **Output (Phase 2)**: A list of attempted paths. If a counterexample is found, provide the path conditions, symbolic variable assignments, and the concrete input values.

#### **Phase 3: Invariant Proving**

*   **Mindset**: You are a **Theorem Proving Specialist**. Your goal is to mathematically prove that the property's assertion holds true for ALL possible execution paths, assuming the analysis from the previous phases found no counterexample.

*   **Procedure**:
    1.  State the original property's assertion as a formal invariant (a logical formula).
    2.  Analyze the results from Phase 1 (Abstract Interpretation) and Phase 2 (Symbolic Execution).
    3.  If Phase 2 found no counterexample, attempt to construct a proof. Use loop invariants, preconditions, and postconditions.
    4.  Does a strong guard condition exist in the code that enforces the invariant? (e.g., `require(x < 100)`).
    5.  If the invariant can be proven to hold true under all conditions, the check passes. If a gap in the logic remains, the check is inconclusive.

*   **Output (Phase 3)**: A summary of the proof attempt. State whether the invariant was proven, and identify the specific guard conditions that enforce it.

### **Task 3.4: Write Outputs**

**THIS STEP MUST HAPPEN BEFORE UPDATING THE QUEUE FILE**

1.  **Generate Partial Audit Map:**
    * Create `outputs/03_AUDITMAP_PARTIAL_W{WORKER_ID}_{TIMESTAMP}_{ITERATION}.json`.
    * Ensure all items in the batch are included.

2.  **Update Worker Queue File:**
    * Add all processed `check_id`s to the `processed` array.
    * **IMPORTANT:** Only update YOUR queue file, not others.
    * Overwrite `QUEUE_FILE`.

---

## 4. Output Format

Produce a JSON object per checklist item (array in the output file) with the following structure:

```json
{
  "check_id": "...",
  "property_id": "...",
  "code_scope": {
    "file": "...",
    "function": "...",
    "line_range": "..."
  },
  "final_classification": "potential-vulnerability | pass | inconclusive",
  "summary": "A one-sentence summary of the final finding.",
  "audit_trail": {
    "phase1_abstract_interpretation": {
      "summary": "...",
      "state_anomalies_found": []
    },
    "phase2_symbolic_execution": {
      "summary": "...",
      "counterexample_found": true,
      "counterexample": {
        "path_conditions": "...",
        "inputs": { "...": "..." },
        "expected_outcome": "..."
      }
    },
    "phase3_invariant_proving": {
      "summary": "Not performed due to counterexample in Phase 2.",
      "proof_successful": false,
      "guard_identified": null
    }
  }
}
```
