
---
Description: Generate a high-fidelity, context-aware audit checklist from a property catalog. This process translates properties into concrete, actionable checks, rigorously filtering for scope and reachability based on an established trust model. The goal is to create targeted, effective checks that focus on verifying mitigations for unreachable attack paths and validating the correct implementation of cryptographic guarantees, thereby minimizing false positives.
Usage: `/02_checklist`
Language: English only.
Execution hint: Run after `/01c_prop`. This is the definitive checklist generation step.
---

**Always use /serena for these development tasks to maximize token efficiency:**

# **Advanced Checklist Creation Prompt (v3)**

**Goal**
Translate every **in-scope** property from the property catalog (`01c_PROP.json`) into a concrete, context-aware checklist item. The checklist must be grounded in the trust model, focusing on verifying mitigations and validating cryptographic guarantees rather than chasing unreachable attack paths.

**Output (required file):** `outputs/02_CHECKLIST.json`

---

## 1) Inputs & Precedence

1.  **Property Catalog (Authoritative):** `outputs/01c_PROP.json`
    *   **This is your primary source of truth.** If missing, halt and report an error.
    *   **CRITICAL:** Only generate checklist items for properties where `status` is `"in_scope"`.
    *   Inherit all fields, especially `property_id`, `trust_scope`, `reachability`, `cryptographic_guarantee`, and `data_flow`.

2.  **Trust Model (Required Context):** `outputs/01b_TRUSTMODEL.json`
    *   Use this to understand the context behind `trust_scope` and why certain actors are considered trusted or untrusted.



3.  **Historical Signals (Optional):** `outputs/01_SIMILAR_ISSUES.json`, `outputs/01_PAST_REPORTS/*`
    *   Use for attack patterns and heuristics **only if the property is reachable**.

---

## 2) The Context-Aware Checklist Generation Logic

For each **in-scope** property from `01c_PROP.json`, apply the following logic to generate the corresponding checklist item. This logic is designed to prevent the creation of checks for issues that are theoretical but not practically exploitable.

### **Logic 1: Handle Unreachable Properties**

*   **If `reachability` is `"UNREACHABLE"`:**
    *   **Do not** create a check to test the `anti_property` directly.
    *   **Instead, create a check to verify the mitigation.** The `title` and `detection_procedure` must focus on confirming that the reason it's unreachable is correctly implemented.
    *   **Title:** Should be phrased as "Verify that [Mitigation] prevents [Anti-Property]".
    *   **Detection Procedure:** Should detail the steps to confirm the mitigating control is in place and effective.
    *   **Example (`reachability` is `UNREACHABLE` due to ZK proof):**
        *   **Bad Check:** "Attempt to inject an arbitrary root into the Hub."
        *   **Good Check:**
            *   `title`: "Verify that the Verifier's ZK proof validation prevents arbitrary root injection into the Hub."
            *   `detection_procedure`: "1. Review `Verifier.sol` to confirm that `proveTransferRoot` is called and successfully validates a Nova proof before a root is stored. 2. Review `Hub.sol` to confirm that `_lzReceive` only accepts messages from the registered Verifier address. 3. Write a test case that attempts to call `relayTransferRoot` without a valid proof, and confirm it reverts."

### **Logic 2: Handle Cryptographically-Guaranteed Properties**

*   **If `cryptographic_guarantee` is not null:**
    *   **Do not** create a check that attempts to break the underlying cryptography.
    *   **Instead, create a check to verify the correct implementation and configuration of the cryptography.**
    *   **Title:** Should be phrased as "Verify the correct implementation of [Cryptographic Guarantee] for [Property]".
    *   **Detection Procedure:** Should focus on checking for common implementation bugs: correct library versions, parameter validation, public input construction, etc.
    *   **Example (`cryptographic_guarantee` is `"Nova Proof Verification"`):
        *   **Bad Check:** "Attempt to forge a Nova proof."
        *   **Good Check:**
            *   `title`: "Verify the correct implementation of Nova proof verification for root transitions."
            *   `detection_procedure`: "1. Confirm that the correct `RootDecider` address is configured in `Verifier.sol`. 2. Verify that all public inputs to the verifier function are correctly constructed and bound. 3. Check for any known vulnerabilities in the specific version of the Nova library being used."

### **Logic 3: Use Data Flow for Realistic Checks**

*   **Use the `data_flow` field from the property to create realistic `executable_checks`.**
*   The test should simulate the actual flow of data through the system, not just an isolated function call.
*   **Example (`data_flow` describes a multi-step process):**
    *   **Bad Check:** `executable_checks`: "Call `Hub.sol` with a fake root."
    *   **Good Check:** `executable_checks`: "1. Create a valid transaction to generate an `IndexedTransfer` event. 2. Run the indexer to process the event. 3. Run the prover to generate a root proof. 4. Tamper with the proof payload *before* submitting it to `Verifier.sol` and confirm it is rejected."

---

## 3) Required Checklist Item Fields (with Advanced Context)

*   `id`: Stable `CL-<DOMAIN>-<BUG-CLASS>-<SLUG>`
*   `property_id`: **Must exactly match** one from `01c_PROP.json`.
*   `title`: **MUST be context-aware** based on the logic in Section 2.
*   `bug_class`
*   `risk_category`
*   `severity_hint`: Can be lowered if `reachability` is low, even if the theoretical impact is high.
*   `trust_scope` (**Inherited from property**).
*   `detection_procedure`: **MUST be context-aware**. If unreachable, describe how to verify the mitigation.
*   `executable_checks`: **MUST be realistic** and follow the `data_flow`.
*   `ok_if`: The condition is met, or the mitigation is verified to be effective.
*   `not_ok_if`: The condition is violated, or the mitigation is found to be flawed.
*   `notes`: **MUST include a rationale** for why the check is designed this way, referencing the property's `reachability` and `cryptographic_guarantee`.
    *   *Example Note:* `"This check focuses on verifying the sender validation in the Hub, as the property's reachability analysis determined a direct root injection is impossible due to upstream proof verification. This addresses the theoretical concern raised in F-002 without chasing a false positive."`

---

## 4) Output Format (JSON)

**File:** `outputs/02_CHECKLIST.json`

Generate a valid JSON object. Ensure you **only create checks for in-scope properties** and that every check is intelligently designed based on the rich context provided by `01c_PROP.json`.

```json
{
  "metadata": {
    "project_name": "zERC20", // From property catalog
    "generated_at": "2025-10-29T11:00:00Z",
    "sources": [
        {
            "title": "Property Catalog",
            "path": "outputs/01c_PROP.json"
        },
        {
            "title": "Trust Model",
            "path": "outputs/01b_TRUSTMODEL.json"
        }
    ],
    "coverage_summary": {
        "total_properties_in_catalog": 50,
        "in_scope_properties": 35,
        "checklist_items_generated": 35,
        "out_of_scope_properties_skipped": 15
    }
  },
  "checklist": [
    {
      "id": "CL-SMART-CONTRACT-STATE-ROOT-INTEGRITY-A4B1",
      "property_id": "PROP-SMART-CONTRACT-ROOT-INTEGRITY-A4B1",
      "title": "Verify that LayerZero sender validation in the Hub prevents unverified root relays",
      "bug_class": "Broken Access Control",
      "risk_category": "integrity",
      "severity_hint": "High", // High because it's a core security mechanism
      "trust_scope": "Untrusted",
      "detection_procedure": [
        "1. Review Hub.sol's `_lzReceive` function.",
        "2. Confirm it uses `_getPeerOrRevert` or an equivalent mechanism to validate that the sender is a registered Verifier.",
        "3. Review the `setPeer` function to ensure only authorized actors can register new Verifiers."
      ],
      "executable_checks": [
        {
          "tool": "Foundry",
          "command": "forge test --match-test testHubRejectsUnregisteredSender",
          "notes": "This test should attempt to call _lzReceive from an arbitrary address and confirm it reverts."
        }
      ],
      "ok_if": "The Hub contract correctly reverts messages from non-registered Verifier addresses.",
      "not_ok_if": "The Hub contract accepts a root update from an arbitrary LayerZero sender.",
      "notes": "This check verifies the primary mitigation for the unreachable property PROP-SMART-CONTRACT-ROOT-INTEGRITY-A4B1. Since the property catalog confirms the anti-property is unreachable due to upstream ZK proof validation, this check focuses on the defense-in-depth mechanism (sender validation)."
    }
    // ... other checklist items
  ]
}
```


---

## 5) Coverage & Validation Loop

**Goal:** Ensure that **every `in_scope` property** from the property catalog is mapped to at least one checklist item.

### Step 1: Generate Coverage Index

After generating all checklist items, create a `coverage` object in the output JSON. This object will track which properties have been covered.

*   **Input:** `outputs/01c_PROP.json` (for the list of `in_scope` properties)
*   **Logic:**
    1.  Create a master list of all `property_id`s from the catalog where `status` is `"in_scope"`.
    2.  For each generated checklist item, check its `property_id` field.
    3.  Mark the corresponding `property_id` from the master list as `covered`.

### Step 2: Identify and Report Gaps

*   **Logic:** Any `property_id` in the master list that is not marked as `covered` is a **gap**.
*   **Output:** Populate the `coverage.gaps` array with any `property_id`s that were not mapped to a checklist item.

### Step 3: Iterative Refinement (The Loop)

*   **CRITICAL RULE:** If the `coverage.gaps` array is **not empty**, you must **re-run the entire checklist generation process** with a specific focus on the `property_id`s listed in the `gaps` array.
*   **Process:**
    1.  Read the `gaps` array from the previous run.
    2.  For each gap, re-evaluate the property and generate a new checklist item using the Context-Aware Checklist Generation Logic.
    3.  Append the new checklist item to the `checklist` array.
    4.  Repeat from Step 1 (Generate Coverage Index).
*   **Termination:** The process is complete only when the `coverage.gaps` array is **empty**.

### Example `coverage` object in `02_CHECKLIST.json`:

```json
{
  // ... metadata and checklist ...
  "coverage": {
    "summary": {
      "in_scope_properties_total": 35,
      "checklist_items_generated": 35,
      "coverage_percentage": 100.0
    },
    "gaps": [] // This MUST be empty for the task to be considered complete.
  }
}
```
