
---
Description: Generate a comprehensive catalog of formal security properties with 100% coverage. If full coverage is not achieved, the process must fail and report the gap.
Usage: `/01e_prop`
Language: English only.
Execution hint: Run after `/01d_trustmodel`. This produces the property catalog.
---
**Always use /serena for development tasks to keep the workflow efficient.**

# **Security Property Catalog Generation Prompt**

**Goal**
Generate a comprehensive catalog of formal security properties with **100% coverage**. If 100% coverage is not achieved, you MUST report this as a failure.

**Output (required file):** `outputs/01e_PROP.json`

---

## 1) Inputs

1.  **System Specification (Authoritative):** `outputs/01_SPEC.json`
2.  **Trust Model (Authoritative):** `outputs/01d_TRUSTMODEL.json`
    - Use `audit_scope` to understand which components are in scope.
    - Use `boundary_edges[].target_component` and `boundary_edges[].target_component_interface` to anchor boundary properties to a specific component and entry point.

---

## 2) Property Generation & Verification Logic

### **Mindset: Adversarial & Comprehensive**

Think like an attacker. For every state, action, and data flow, ask: "How could this be abused?" Your goal is to create properties that, if formally verified, would prove the system is resilient to these abuses.

### **Task 2.1: Generate Properties by Type and Priority**

#### **Priority 1: Boundary Edge Properties (Input Validation)**

For each `boundary_edge` in `01d_TRUSTMODEL.json`, generate multiple, high-priority properties. These are the most critical properties. Use the edge's `target_component` and `target_component_interface` to make the properties specific to the entry point and component boundary.

*   **Property Type:** `Pre-condition`
*   **Focus:** Validate every field of the incoming `data_flows_across` (or equivalent inputs for the interface). Tie the property to the exact entry point.
*   **Example:** For a `boundary_edge` where a transaction is received:
    *   **Good Property 1 (Format):** "At `eth_sendRawTransaction` on the EL, the `gas_limit` field must be a valid unsigned 64-bit integer."
    *   **Good Property 2 (Range):** "At `eth_sendRawTransaction` on the EL, the `gas_limit` must be greater than the intrinsic gas cost of the transaction."
    *   **Good Property 3 (Cryptographic):** "At `eth_sendRawTransaction` on the EL, the transaction's ECDSA signature (v, r, s) must be valid and correspond to the `sender` address."

#### **Priority 2: Ambiguity & Assumption Properties**

For each `ambiguity` and `implicit_assumption` in `01_SPEC.json`, generate a corresponding property.

*   **Property Type:** `Invariant` or `Pre-condition`
*   **Focus:** Formalize the assumption or the chosen resolution strategy.
*   **Example:** For an assumption `ASSUM-EIP4844-01` ("An attacker cannot create a valid blob transaction without paying gas fees."):
    *   **Good Property:** "For any `ACTION-PROCESS-BLOB-TX`, the associated `STATE-ACCOUNT-BALANCE` of the sender must be greater than or equal to the calculated `blob_gas_fee`."

#### **Priority 3: Internal State Transition Properties**

For internal edges (especially those originating from an `Action` node), generate properties that define correct state transitions.

*   **Property Type:** `Post-condition`
*   **Focus:** Define what must be true after an action completes.
*   **Example:** For an edge `ACTION-EXECUTE-TX` -> `STATE-TX-COMPLETE`:
    *   **Good Property:** "After `ACTION-EXECUTE-TX` completes, the `nonce` of the sender's account state must be incremented by one."

#### **Priority 4: General Invariants**

Generate properties that must hold true for all states.

*   **Property Type:** `Invariant`
*   **Focus:** System-wide safety and consistency rules.
*   **Example:**
    *   **Good Property:** "The total supply of Ether in the system must never decrease, except through the burning mechanism defined in EIP-1559."

### **Task 2.2: CRITICAL - Coverage Verification**

**This is a mandatory verification step.**

1.  Create a set of all node IDs from `01_SPEC.json`.
2.  Create a set of all edge IDs from `01_SPEC.json`.
3.  Create a set of all node and edge IDs covered by the `graph_elements` field in the properties you just generated.
4.  **Calculate `nodes_uncovered`:** The set of spec nodes minus the set of covered nodes.
5.  **Calculate `edges_uncovered`:** The set of spec edges minus the set of covered edges.

### **Task 2.3: Finalize Output**

1.  **Assemble the `properties` array.**
2.  **Calculate all metadata and `coverage_summary` values** based on the final generated data.
3.  **Check Verification Result:**
    *   **If `nodes_uncovered` and `edges_uncovered` are both empty:** Set `coverage_percentage` to `100.0` and `coverage_ok` to `true`.
    *   **If either set is not empty:** Set `coverage_percentage` to the calculated value, set `coverage_ok` to `false`, and populate the `uncovered_elements` field.

---

## 3) Required Output Format (JSON)

**File:** `outputs/01e_PROP.json`

```json
{
  "metadata": {
    "generated_at": "(current timestamp)",
    "total_properties": "(calculated count)"
  },
  "coverage_summary": {
    "total_nodes": "(calculated count)",
    "nodes_covered": "(calculated count)",
    "total_edges": "(calculated count)",
    "edges_covered": "(calculated count)",
    "coverage_percentage": "(calculated percentage)",
    "coverage_ok": "(boolean, true if 100%, otherwise false)",
    "uncovered_elements": {
        "nodes": [ /* list of uncovered node IDs, if any */ ],
        "edges": [ /* list of uncovered edge IDs, if any */ ]
    }
  },
  "properties": [
    {
      "id": "PROP-TX-001",
      "title": "Transaction Signature Validity",
      "description": "The ECDSA signature of any submitted transaction must be cryptographically valid and correspond to the derived sender address.",
      "type": "Pre-condition",
      "priority": "CRITICAL",
      "is_boundary_check": true,
      "graph_elements": ["EDGE-USER-SUBMIT-TX"],
      "related_assumption_id": null,
      "related_ambiguity_id": null
    }
  ]
}
```
