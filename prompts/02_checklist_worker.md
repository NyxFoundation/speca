
---
Description: [UNIFIED PARALLEL WORKER] Generate checklist items for all property types (boundary and internal).
Usage: `/02_checklist_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...]`
Example: `/02_checklist_worker WORKER_ID=0 QUEUE_FILE=outputs/02_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1`
Language: English only.
Execution hint: This is a unified worker prompt for parallel execution. Called by run_worker.py.
---
**Always use /serena for these development tasks to maximize token efficiency:**

# **Unified Checklist Generation (Parallel Worker)**

**Goal**
Generate audit checklist items for properties assigned to this worker's queue. Process a dynamic batch of properties, applying the correct security mindset based on whether the property covers a trust boundary or internal logic.

## Worker Configuration

- **`WORKER_ID`**: The numeric ID of this worker (0, 1, 2, ...)
- **`QUEUE_FILE`**: Path to this worker's queue file (e.g., `outputs/02_QUEUE_0.json`)
- **`TIMESTAMP`**: Unix timestamp for this iteration (used in output naming)
- **`ITERATION`**: The current iteration number for this worker

**Output:** `outputs/02_CHECKLIST_PARTIAL_W{WORKER_ID}_{TIMESTAMP}_{ITERATION}.json`

---

## 1) Inputs

1.  **Worker Queue File:** `QUEUE_FILE`
    -   Contains `items`: a list of objects, each with `property_id` and `source_file`.
    -   Contains `processed`: a list of already processed `property_id` values.

2.  **Property Partial Files:** `outputs/01e_PROP_PARTIAL_*.json` (loaded on-demand based on `source_file`)
3.  **Trust Model Partials:** `outputs/01d_TRUSTMODEL_PARTIAL_*.json` (loaded on-demand for boundary properties)

---

## 2) Worker Execution Logic

### **Task 2.1: Read Worker Queue & Prepare Batch**

1.  Read the worker queue file `QUEUE_FILE`.
2.  Identify unprocessed items (property IDs in `items` but not in `processed`).
3.  If no items remain, terminate successfully.
4.  **Create a dynamic batch**: Take unprocessed items **until the cumulative size of their unique `source_file`s reaches ~120KB** (approximately **30,000 tokens**). This batch will contain a variable number of properties.
    -   Estimate each property file's token count as: `file_size_bytes / 4`
    -   Keep a running total as you add unique `source_file`s
    -   Stop adding files when: `cumulative_tokens + next_file_tokens > 30,000`
    -   If the batch is empty (first file > 120KB), process that single file alone

### **Task 2.2: Process Batch**

1.  **Load Necessary Files**: Read only the unique `source_file`s required for the current batch of properties.

2.  **For EACH property in the batch:**

    #### **A. Filter Out-of-Scope Properties (NEW)**

    -   Read the property's data from the loaded partial file.
    -   If `reachability.bug_bounty_scope == "out-of-scope"`, **skip** this property.
    -   If `exploitability == "api-only"` or `exploitability == "configuration-error"`, **skip** this property.
    -   **Exception**: If `reachability.bug_bounty_scope == "conditional"`, include it but add a note that it requires further investigation.
    -   If `reachability` is missing, consult any Bug Bounty Scope block provided at the top of this prompt (or `outputs/BUG_BOUNTY_SCOPE.json`) to infer scope, and note the inference.

    #### **B. Determine Property Type & Mindset**

    -   Read the property's data from the loaded partial file.
    -   Check if `covers.is_boundary_edge == true`.
    -   **If TRUE (Boundary Property):**
        -   **Adopt Mindset: "Boundary Guard"**. You are securing the system's perimeter. Your focus is on untrusted data and external interactions.
        -   **Load Context**: Find the corresponding `boundary_edge` in the `01d_TRUSTMODEL_PARTIAL_*.json` files to get the `target_component`, `target_component_interface`, `trust_level`, and `archetypal_attack_vectors`.
    -   **If FALSE (Internal Property):**
        -   **Adopt Mindset: "Formal Verification Engineer"**. You are proving the correctness of the system's internal logic.

    #### **C. Generate Checklist Items**

    -   **If a Boundary Property:**
        1.  **Generate a CRITICAL Boundary Check**: Create one checklist item specifically for the `boundary_edge` itself. The title must be `"Verify Trust Boundary Integrity for {EDGE_ID}..."`. The `detection_procedure` should focus on input validation, authentication, and data sanitization at the specific entry point.
        2.  **Generate Supporting Node Checks**: Create additional checklist items for the `nodes` covered by the property. These checks should verify how the internal logic supports the boundary's security (e.g., validating data *after* it has crossed the boundary).

    -   **If an Internal Property:**
        1.  **Generate ONE Falsification Check**: Create a single checklist item focused on the property's `primary_element`. The goal is to design a test that attempts to **falsify** the property.
        2.  Tailor the check to the property `type`:
            -   `Invariant`: Design a test to violate the invariant through state transitions.
            -   `Pre-condition`: Design a test to bypass the condition with invalid inputs.
            -   `Post-condition`: Design a test to verify side-effects and check for unexpected state changes.

    #### **D. Checklist Item Format (Unified)**

    -   `id`: `CHECK-W{WORKER_ID}-{PROP_ID}-{TYPE}` (e.g., BOUNDARY, NODE, INTERNAL)
    -   `property_id`: Source property ID.
    -   `graph_element_under_test`: Node or edge ID being audited.
    -   `title`: Clear, actionable title reflecting the mindset.
    -   `reachability`: Copy from the property (include `entry_points`, `attacker_controlled`, `bug_bounty_scope`).
    -   `bug_class`, `risk_category`, `severity_hint`, `detection_procedure`, `executable_checks`: All required.
    -   `notes`: **MUST** include traceability back to the source property and graph elements.

### **Task 2.3: Write Outputs (Atomic & Strict)**

**Output MUST be valid JSON. Do NOT use expressions, concatenation, comments, or trailing commas.**

1.  **Generate Partial Checklist (atomic write):** Create `outputs/02_CHECKLIST_PARTIAL_W{WORKER_ID}_{TIMESTAMP}_{ITERATION}.json` containing all checks generated for the batch. Write to a temporary file first, then atomically rename to the final path.
2.  **Update Worker Queue:** **DO NOT UPDATE THE QUEUE FILE.**
    * The runner script (`run_worker.py`) will update `processed` atomically after validating your output.

---

## 3) Required Output Format (JSON)

**Partial Checklist:** `outputs/02_CHECKLIST_PARTIAL_W{WORKER_ID}_{TIMESTAMP}_{ITERATION}.json` (set `metadata.batch` to `ITERATION`)

```json
{
  "metadata": {
    "worker_id": 0,
    "batch": 1,
    "stage": "02_unified",
    "source_files": ["outputs/01e_PROP_PARTIAL_W0_1.json"],
    "properties_processed": 15,
    "total_checks": 25
  },
  "checklist": [
    // ... checklist items for both boundary and internal properties ...
  ]
}
```

**Each checklist item MUST include a `reachability` object copied from the property.**

---

## 4) Quality Requirements

-   **Mindset-Driven**: The tone and focus of each check must reflect the correct mindset (Boundary Guard vs. Formal Verification Engineer).
-   **On-Demand Data**: The process must not rely on loading entire catalogs. All external data (properties, trust models) is loaded as needed.
-   **Traceability**: Every check must be traceable to a source property.
-   **Actionable**: Procedures must be specific and verifiable.
-   **Scope-Aware**: Out-of-scope properties are filtered out; conditional scope is noted.
