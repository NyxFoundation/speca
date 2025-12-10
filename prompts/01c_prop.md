
---
Description: Derive a high-fidelity, context-aware property catalog from the system specification and the trust model. This prompt translates normative behaviors into `{property, anti_property}` tuples, rigorously filtering out-of-scope items and explicitly grounding each property in the established trust model to prevent false positives.
Usage: `/01c_prop`
Language: English only.
Execution hint: Run after `/01_spec` and `/01b_trustmodel`. This is the definitive property generation step.
---

**Always use /serena for these development tasks to maximize token efficiency:**

# **Advanced Property Extraction Prompt (v3)**

**Goal**
Translate every normative behavior from the specification into actionable, trust-model-aware property tuples. This process involves a rigorous 6-step validation to ensure every property is in-scope, contextually relevant, and directly traceable to the system's architecture and trust boundaries.

**Output (required file):** `outputs/01c_PROP.json`
**Determinism:** Sort all top-level arrays deterministically by `id`.

---

## 1) Inputs & Authority

1.  **Trust Model (Authoritative):** `outputs/01b_TRUSTMODEL.json`
    *   **This is your primary source of truth for trust assumptions.**
    *   If missing, halt and report an error.
    *   Inherit `actors`, `components`, `trust_level`, `capabilities_if_malicious`, and `mitigations`.

2.  **Specification (Supporting):** `outputs/01_SPEC.json`
    *   Use `user_flows` and `algorithms` to understand intended behavior.
    *   If the spec contradicts the trust model, **the trust model takes precedence.**

3.  **Bounty/Audit Scope (Filter):** `outputs/01_BOUNTY_GUIDELINE.md` (if it exists)
    *   Use the `Out of Scope` section to filter out irrelevant properties early.

---

## 2) The 6-Step Property Validation Gauntlet

For every potential property derived from the specification, you **MUST** run it through this 6-step gauntlet. If a property fails any of these checks, it should either be discarded or marked as `out_of_scope` with a clear reason.

### **Step 1: Is it explicitly Out of Scope?**
*   **Check:** Does the property fall under any category listed in `01_BOUNTY_GUIDELINE.md`'s `Out of Scope` section?
*   **Action:** If yes, create a property tuple but mark it: `"status": "out_of_scope"` and `"out_of_scope_reason": "Listed in bounty guidelines (e.g., trusted setup)"`. Do not proceed further.
*   **Example:** A property related to the security of the trusted setup ceremony.

### **Step 2: Is it an Operational or a Code-Level Issue?**
*   **Check:** Does exploiting this property require compromising the environment (e.g., server access, private keys) rather than interacting with the code's public interface?
*   **Action:** If operational, mark it as `"category": "operational"` and `"status": "out_of_scope"`.
*   **Example:** An attacker with root access to the indexer server can halt the service.

### **Step 3: Is it a Feature or a Bug?**
*   **Check:** Is this behavior described as intended in the `01_SPEC.json`?
*   **Action:** If it's a feature, do not create a property for it being a vulnerability.
*   **Example:** A contract owner having the ability to upgrade the contract is a feature, not a bug.

### **Step 4: Does it require a Privileged Role?**
*   **Check:** Can this `anti_property` only be realized by an actor with a privileged role (e.g., `Owner`, `Admin`, `Deployer`) as defined in `01b_TRUSTMODEL.json`?
*   **Action:** If yes, mark `"requires_privileged_role": true` and `"status": "out_of_scope"`.
*   **Example:** A contract owner pausing the contract.

### **Step 5: Is it protected by a Cryptographic Guarantee?**
*   **Check:** Is the state transition or data integrity protected by a cryptographic primitive (e.g., ZK proof, digital signature, hash commitment)?
*   **Action:** If yes, explicitly state this in the `cryptographic_guarantee` field. Do not create properties that assume the cryptography is broken unless the goal is to test the implementation of the cryptography itself.
*   **Example:** A property assuming a user can create a valid withdrawal proof without a valid burn event. This is prevented by the ZK proof system.

### **Step 6: Is it protected by a different layer?**
*   **Check:** Is this property checked or enforced in a different system layer (e.g., a smart contract value being constrained by a ZK circuit)?
*   **Action:** If yes, document this in the `enforcement_scope`. A property might be valid but have its risk lowered because of cross-layer protection.
*   **Example:** A value overflow in a smart contract might be impossible because the value is proven to be in a smaller range by a ZK circuit.

---

## 3) Advanced Property Derivation

After a potential property survives the gauntlet, create a full property tuple with the following advanced fields:

*   **`property_id`**: `PROP-<DOMAIN>-<SLUG>-<H4>`
*   **`property`**: Declarative invariant (what should always be true).
*   **`anti_property`**: Attacker-centric failure mode.
*   **`trust_scope` (Inherited)**: **MUST** be inherited directly from the `trust_level` of the relevant actor in `01b_TRUSTMODEL.json`. If the trust model is `UNCLEAR`, this field must also be `UNCLEAR`.
*   **`enforcement_scope`**: Where the property is enforced (e.g., `contract:Verifier.sol`, `circuit:withdraw`, `off-chain:indexer`).
*   **`data_flow`**: A concise description of the data's lifecycle relevant to this property. 
    *   *Example:* "Root is generated by the on-chain `proveTransferRoot` function (which verifies a proof), stored in `provedTransferRoots`, and then relayed to the Hub."
*   **`reachability`**: Analysis of whether the `anti_property` is actually reachable in a real-world scenario.
    *   *Example:* `"UNREACHABLE: The Hub only accepts roots from a trusted Verifier contract, which in turn only creates roots after successful proof verification. An arbitrary root injection is not possible."`
*   **`cryptographic_guarantee`**: The specific cryptographic mechanism that protects this property.
    *   *Example:* `"Nova Proof Verification"`
*   **`operational_prerequisite`**: Any operational setup required for this property to hold.
    *   *Example:* `"A valid and secure trusted setup for the Groth16 parameters."`
*   **`status`**: `"in_scope"`, `"out_of_scope"`, `"needs_clarification"`.
*   **`out_of_scope_reason`**: Justification if `status` is `out_of_scope`.
*   **`notes`**: Any additional context, including references to the trust model.
    *   *Example:* `"This property's trust scope is set to Untrusted, as it relates to the Indexer, which is defined as a permissionless and untrusted actor in 01b_TRUSTMODEL.json."`

---

## 4) Output Format (JSON)

**File:** `outputs/01c_PROP.json`

Generate a valid JSON object. Ensure every property has passed through the 6-step validation gauntlet and is explicitly linked to the trust model.

```json
{
  "metadata": {
    "project_name": "zERC20", // From 01_SPEC.json
    "prop_generated_at": "2025-10-29T10:00:00Z",
    "sources": [
      {
        "title": "Trust Model",
        "path": "outputs/01b_TRUSTMODEL.json"
      },
      {
        "title": "Project Specification",
        "path": "outputs/01_SPEC.json"
      },
      {
        "title": "Bounty Guidelines",
        "path": "outputs/01_BOUNTY_GUIDELINE.md"
      }
    ]
  },
  "properties": [
    {
      "property_id": "PROP-SMART-CONTRACT-ROOT-INTEGRITY-A4B1",
      "property": "The Hub contract only accepts transfer roots that have been cryptographically verified by a registered Verifier contract.",
      "anti_property": "An attacker can inject an arbitrary or unverified transfer root into the Hub contract.",
      "trust_scope": "Untrusted", // Inherited from the trust level of the message sender (e.g., any off-chain relayer)
      "enforcement_scope": ["contract:Hub.sol#_lzReceive", "contract:Verifier.sol#relayTransferRoot"],
      "data_flow": "A root is verified in Verifier.sol -> stored in provedTransferRoots -> relayed to Hub.sol via LayerZero -> Hub.sol verifies the sender is a registered Verifier.",
      "reachability": "UNREACHABLE. The anti_property is not reachable because Hub.sol's `_lzReceive` function validates that the message sender is a known Verifier, and the Verifier only relays roots that have passed ZK proof verification.",
      "cryptographic_guarantee": "Nova Proof Verification in Verifier.sol",
      "operational_prerequisite": null,
      "requires_privileged_role": false,
      "status": "in_scope",
      "out_of_scope_reason": null,
      "notes": "This property directly addresses the false positive F-002. The key mitigation is the combination of ZK proof verification and LayerZero's trusted remote sender validation."
    },
    {
      "property_id": "PROP-OPERATIONAL-TRUSTED-SETUP-C3D2",
      "property": "The Groth16 parameters are generated via a secure multi-party computation ceremony.",
      "anti_property": "An attacker can generate malicious Groth16 parameters, compromising the soundness of the proof system.",
      "trust_scope": "Trusted", // The deployer/ceremony organizers
      "enforcement_scope": ["operational:setup_ceremony"],
      "data_flow": null,
      "reachability": "REACHABLE but out of scope for a code audit.",
      "cryptographic_guarantee": null,
      "operational_prerequisite": "Execution of a secure MPC ceremony.",
      "requires_privileged_role": true, // Requires being a participant in the setup
      "status": "out_of_scope",
      "out_of_scope_reason": "Listed in bounty guidelines (trusted setup) and is an operational issue, not a code-level vulnerability.",
      "notes": "This addresses the false positives F-008, F-009, F-012. The security of the code assumes the operational prerequisite of a secure setup."
    }
  ]
}
```


---

## 5) Coverage & Validation Loop

**Goal:** Ensure that **every** normative behavior from the specification is mapped to at least one property, whether `in_scope` or `out_of_scope`.

### Step 1: Generate Coverage Index

After generating all properties, create a `coverage` object in the output JSON. This object will track which parts of the specification have been covered.

*   **Input:** `outputs/01_SPEC.json` (for `domains`, `user_flows`, `algorithms`)
*   **Logic:**
    1.  Create a master list of all normative items from the spec (e.g., `FLOW-001`, `ALGO-COMMIT-VERIFY`).
    2.  For each generated property, check its `spec_refs` field.
    3.  Mark the corresponding normative items from the master list as `covered`.

### Step 2: Identify and Report Gaps

*   **Logic:** Any item in the master list that is not marked as `covered` is a **gap**.
*   **Output:** Populate the `coverage.gaps` array with any items that were not mapped to a property.

### Step 3: Iterative Refinement (The Loop)

*   **CRITICAL RULE:** If the `coverage.gaps` array is **not empty**, you must **re-run the entire property generation process** with a specific focus on the items listed in the `gaps` array.
*   **Process:**
    1.  Read the `gaps` array from the previous run.
    2.  For each gap, re-evaluate the specification and generate a new property tuple.
    3.  Run this new property through the 6-Step Validation Gauntlet.
    4.  Append the new property to the `properties` array.
    5.  Repeat from Step 1 (Generate Coverage Index).
*   **Termination:** The process is complete only when the `coverage.gaps` array is **empty**.

### Example `coverage` object in `01c_PROP.json`:

```json
{
  // ... metadata and properties ...
  "coverage": {
    "summary": {
      "spec_items_total": 15,
      "properties_generated": 15,
      "coverage_percentage": 100.0
    },
    "gaps": [] // This MUST be empty for the task to be considered complete.
  }
}
```
