
---
Description: [PARALLEL WORKER] Iteratively generate audit checklist items for properties from a worker-specific queue. This prompt is designed to be run multiple times (Stage 2).
Usage: `/02b_checklistrem_worker WORKER_ID=... QUEUE_FILE=...`
Example: `/02b_checklistrem_worker WORKER_ID=0 QUEUE_FILE=outputs/02b_QUEUE_0.json`
Language: English only.
Execution hint: This is a worker prompt for parallel execution. Called by run_worker.py.
---
**Always use /serena for these development tasks to maximize token efficiency:**

# **Checklist Generation (Parallel Worker - Stage 2: Remaining Properties)**

**Mindset: You are a Formal Verification Engineer. Your goal is not just to find bugs, but to mathematically prove the correctness of the system's internal logic by testing its fundamental properties.**

**Goal**
Generate audit checklist items for properties assigned to this worker's queue. Process a batch of properties and output checklist items with worker-specific naming. This prompt is designed to be run multiple times. It reads a worker queue file to determine which properties are left to process, generates checks for a small batch, and then writes the remaining work back to the queue file for the next run.

## Worker Configuration

This is **parallel worker `WORKER_ID`**. You have a dedicated queue file that only you read from and write to.

- **`WORKER_ID`**: The numeric ID of this worker (0, 1, 2, ...)
- **`QUEUE_FILE`**: Path to this worker's queue file (e.g., `outputs/02b_QUEUE_0.json`)

**Output (required files):**
1.  `outputs/02b_CHECKLIST_PARTIAL_W<WORKER_ID>_<N>.json`: A partial checklist for the current batch. `<N>` is the batch number.
2.  Worker queue file: Updated with processed property IDs.

---

## 1) Inputs

1.  **Property Catalog (Authoritative):** `outputs/01e_PROP.json`
2.  **Worker Queue File:** `QUEUE_FILE`
    - Contains `items`: list of property IDs assigned to this worker
    - Contains `processed`: list of already processed property IDs

---

## 2) Worker Execution Logic

Your task is to manage a queue of properties and process a small batch in each run.

### **Task 1: Read Worker Queue**

1.  Read the worker queue file `QUEUE_FILE`
2.  Get the list of `items` (all assigned property IDs)
3.  Get the list of `processed` (already done property IDs)
4.  Calculate remaining: property IDs in `items` but not in `processed`
5.  If no remaining property IDs, terminate successfully. The checklist generation for this worker is complete.
6.  Take the **first 20 unprocessed property IDs** as your batch for this run (or fewer if less than 20 remain).

### **Task 2: Process a Batch of Properties**

1.  **Take a Batch:** From your remaining queue, take the **first 20 property IDs**. This is your batch for this run.
2.  **Generate Checks (Sampling Approach):** For each of the 20 properties in your batch, you **MUST** generate **exactly one** checklist item.
    *   This single check should focus on the property's `primary_element` as defined in its `covers` object.
    *   **CRITICAL:** Do NOT iterate through all `graph_elements` for a property. Generate only one check per property to keep the output manageable.
3.  **Identify the Property's Logical Purpose:**
    *   Read the property's `natural_language` (description) and `type` (e.g., `Invariant`, `Pre-condition`, `Post-condition`).
    *   Understand **WHY** this property exists and what fundamental aspect of correctness it represents.
4.  **Design each checklist item** using the same high-quality standards as in Stage 1, and align `detection_procedure` and `bug_class` to the property type:
    *   If `type` is `Invariant`: try to **violate** the invariant by probing state transitions; include continuous monitoring checks.
        *   `bug_class`: "State Management", "Concurrency"
    *   If `type` is `Pre-condition`: try to **bypass** the condition with invalid inputs.
        *   `bug_class`: "Input Validation", "Access Control"
    *   If `type` is `Post-condition`: verify **side-effects** and return values; ensure no unexpected effects.
        *   `bug_class`: "State Management", "Error Handling"
5.  **Design each checklist item** with the required fields:
    *   `id`: Unique identifier (e.g., `CHECK-W{WORKER_ID}-{PROP_ID}-001`)
    *   `property_id`: The source property ID
    *   `title`: Descriptive title that clearly states what is being checked
    *   `bug_class`: Type of vulnerability (e.g., "Input Validation", "State Management", "Access Control", "Resource Management", "Cryptographic", "Concurrency")
    *   `severity_hint`: Expected severity (Critical, High, Medium, Low)
    *   `detection_procedure`: Detailed step-by-step procedure for how to detect the issue
    *   `executable_checks`: Specific verification steps that can be performed
    *   `notes`: Additional context, edge cases, or related considerations

### **Task 3: Write Outputs**

1.  **Generate Partial Checklist:**
    *   Determine the batch number by counting existing `02b_CHECKLIST_PARTIAL_W{WORKER_ID}_*.json` files + 1
    *   Create a file named `outputs/02b_CHECKLIST_PARTIAL_W{WORKER_ID}_{BATCH}.json`
    *   This file will contain the `metadata` and a `checklist` array with the ~20 items you just generated.
    *   Include `worker_id` and `batch_number` in metadata.

2.  **Update Worker Queue File:**
    *   Add ALL processed property IDs from this batch to the `processed` array.
    *   **IMPORTANT:** Only update YOUR queue file, not others.
    *   Overwrite `QUEUE_FILE` with the updated state.

---

## 3) Required Output Format (JSON)

**Partial Checklist File:** `outputs/02b_CHECKLIST_PARTIAL_W{WORKER_ID}_{BATCH}.json`
```json
{
  "metadata": {
    "worker_id": 0,
    "batch_number": 1,
    "generated_at": "2025-12-23T10:00:00Z",
    "properties_processed": 20
  },
  "checklist": [
    {
      "id": "CHECK-W0-PROP-NODE-STATE-TX-INVALID-001",
      "property_id": "PROP-NODE-STATE-TX-INVALID-001",
      "title": "Verify transaction invalidation on signature failure",
      "bug_class": "Input Validation",
      "severity_hint": "High",
      "detection_procedure": "1. Identify all entry points where transactions are received (RPC, P2P). 2. Trace the signature validation code path. 3. Verify that invalid signatures result in transaction rejection. 4. Check for any bypass paths that skip validation.",
      "executable_checks": [
        "Verify all signature types (legacy, EIP-2930, EIP-1559) are validated",
        "Confirm invalid signatures lead to transaction rejection with appropriate error",
        "Check that partially valid signatures are rejected",
        "Verify signature validation cannot be bypassed via alternate code paths"
      ],
      "notes": "Focus on edge cases in signature encoding. Consider: empty signatures, malformed r/s values, invalid recovery IDs, signatures from wrong chain ID."
    },
    {
      "id": "CHECK-W0-PROP-NODE-ACTION-VALIDATE-BLOCK-001",
      "property_id": "PROP-NODE-ACTION-VALIDATE-BLOCK-001",
      "title": "Verify block validation rejects malformed headers",
      "bug_class": "Input Validation",
      "severity_hint": "Critical",
      "detection_procedure": "1. Identify block validation entry points. 2. Enumerate all header fields that must be validated. 3. Verify each field has appropriate validation. 4. Test with malformed headers.",
      "executable_checks": [
        "Verify parent hash validation",
        "Confirm timestamp bounds checking",
        "Check gas limit delta constraints",
        "Verify difficulty/nonce validation (pre-merge) or withdrawals root (post-merge)"
      ],
      "notes": "Block validation is critical for consensus. Any bypass could lead to chain splits or invalid state acceptance."
    }
  ]
}
```

**Updated Worker Queue File:** `QUEUE_FILE`
```json
{
  "worker_id": 0,
  "phase": "02b",
  "total_workers": 4,
  "items": ["PROP-001", "PROP-002", "PROP-003", "..."],
  "processed": ["PROP-001", "PROP-002"],
  "total_items": 50
}
```

---

## 4) Quality Requirements

Each checklist item must be:

- **Specific:** Reference concrete code patterns, behaviors, or properties. Avoid vague statements.
- **Actionable:** Provide clear steps that an auditor can follow to verify the property.
- **Prioritized:** Include severity hints based on potential security impact.
- **Traceable:** Link back to source property ID for full traceability.
- **Comprehensive:** Cover the key aspects of the property's `primary_element`.

### Checklist Item Design Guidelines

**For `detection_procedure`:**
- Write step-by-step instructions
- Be specific about what code paths to examine
- Include both positive (should happen) and negative (should not happen) checks

**For `executable_checks`:**
- Each check should be independently verifiable
- Checks should be concrete enough to produce a pass/fail result
- Include edge cases and boundary conditions

**For `bug_class`:**
- Use consistent categories across all items
- Common classes: Input Validation, State Management, Access Control, Resource Management, Cryptographic, Concurrency, Error Handling

**For `severity_hint`:**
- Critical: Direct loss of funds, consensus failure, remote code execution
- High: Significant security impact, DoS, data corruption
- Medium: Limited security impact, requires specific conditions
- Low: Minor issues, code quality concerns

This iterative process ensures that even if a single run is interrupted or hits a token limit, the next run can seamlessly continue from where the last one left off, guaranteeing the eventual generation of a complete checklist.
