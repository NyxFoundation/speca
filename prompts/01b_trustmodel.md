

---
Description:
Construct a detailed, operation-centric Trust Model by analyzing system architecture, specifications, and potential operational configurations. This model will identify all actors, components, and their trust boundaries, serving as the foundational security context for all subsequent audit phases.

Usage: `/01b_trustmodel`
Language: English only.
Execution hint: Run after `/01_spec` but before `/01c_prop`. This ensures the trust model is established before properties are extracted, preventing the propagation of incorrect trust assumptions.
---

**Always use /serena for these development tasks to maximize token efficiency:**


# **Trust Model Construction Prompt**

**Goal**
From the provided system specifications and code, construct a comprehensive Trust Model that explicitly defines all actors, their capabilities, and the trust assumptions between them. The primary focus is to reverse-engineer the trust model from **operational flows**, considering all plausible deployment and operational scenarios.

**Output (required file):** `security-agent/outputs/01b_TRUSTMODEL.json`
**Determinism:** Sort all top-level arrays deterministically by `id`.

---

## 1) Inputs & Authority

1.  **Primary Spec (Authoritative):** `security-agent/outputs/01_SPEC.json`
    *   Use `trusted_entities`, `user_flows`, and `algorithms` as the primary source of documented behavior.
    *   If the spec is missing, halt and report an error.

2.  **Architecture & Code (Supporting):**
    *   Recursively scan the source directory (`metadata.source_directory` from the spec) for architecture diagrams, deployment scripts (`docker-compose.yml`, `*.tf`, `*.yaml`), configuration files, and code comments that reveal operational roles and interactions.

3.  **External Research (Optional but Recommended):**
    *   Consult `metadata.reference_urls` for similar architectures or protocols. For example, when analyzing a cross-chain bridge, review the documented trust models of LayerZero, Wormhole, or Nomad to understand common patterns and pitfalls.

---

## 2) Trust Model Derivation: An Operation-Centric Approach

Your primary task is to think like a system operator and a security architect. For every component and interaction, you must analyze the **operational reality** of who runs what, and what incentives they have.

### Step 1: Identify All Actors & Components

*   **Actors:** Enumerate every entity that interacts with the system, both human and automated.
    *   **On-Chain:** `Deployer`, `Owner`/`Admin`, `User`, `Governance`, `Contract Upgrader`.
    *   **Off-Chain:** `Indexer`, `Prover`, `Decider`, `Relayer`, `Oracle`, `API User`, `Frontend User`, `System Operator`.
    *   **External:** `LayerZero Relayer`, `Chainlink Oracle`, `External Bridge Operator`.
*   **Components:** List all key software/hardware modules.
    *   **On-Chain:** Smart Contracts (`Verifier.sol`, `Hub.sol`), Proxy Contracts.
    *   **Off-Chain:** Services, databases, message queues (e.g., `Postgres`, `Redis`).
    *   **External:** LayerZero Endpoints, ICP Canisters, other blockchains.

### Step 2: Analyze Operational Scenarios & Configurations

For each off-chain actor/component, you **MUST** consider different operational configurations. Do not assume a single deployment model unless explicitly stated in the documentation.

**Thought Process Example:**
> Who runs the **Indexer**?
>
> *   **Scenario A: Centralized (Protocol Team):** The core developers run the indexer.
>     *   *Trust Implication:* Trusted for liveness, but what if they become malicious? Can they censor data?
> *   **Scenario B: Permissioned Federation:** A known set of partners runs indexers.
>     *   *Trust Implication:* Trust is distributed. What is the threshold for collusion (e.g., 2/3)?
> *   **Scenario C: Permissionless:** Anyone can run an indexer.
>     *   *Trust Implication:* Untrusted for liveness. The system must be safe even if all indexers are malicious. How does the protocol protect against a malicious indexer (e.g., on-chain verification)?
> *   **Documentation Check:** Does `01_SPEC.json` or any architecture diagram specify this? If not, mark as `UNCLEAR` and analyze all plausible scenarios.

### Step 3: Define Trust Levels and Capabilities for Each Actor

For each actor identified in Step 1, create a detailed profile.

*   **`id`**: A unique identifier (e.g., `ACTOR-OFFCHAIN-INDEXER`).
*   **`name`**: Human-readable name (e.g., "Off-Chain Indexer").
*   **`description`**: What is its role in the system?
*   **`operational_scenarios`**: A list of possible operational configurations (from Step 2).
*   **`trust_level`**: Assign one of the following, **per scenario**:
    *   `Trusted`: Assumed to be honest and available. A compromise breaks core safety guarantees.
        *   *Example:* The contract `Deployer` during initial setup.
    *   `Semi-Trusted` / `Conditionally_Trusted`: Trusted for liveness but not for safety. The system can tolerate malicious behavior to a certain extent.
        *   *Example:* A LayerZero relayer is trusted to relay messages, but the content of the messages is verified on-chain.
    *   `Untrusted`: Assumed to be potentially malicious. The system must remain safe even if this actor is fully compromised.
        *   *Example:* Any `User` of a permissionless protocol.
*   **`capabilities_if_honest`**: What actions can this actor perform when behaving correctly?
*   **`capabilities_if_malicious`**: What is the maximum damage this actor can cause if they are malicious or compromised? Be specific.
    *   *Good:* "A malicious indexer can censor specific transactions by omitting them from the Merkle tree, causing a liveness failure for the affected users."
    *   *Bad:* "The indexer can cause problems."
*   **`mitigations`**: What mechanisms in the protocol limit the power of a malicious actor?
    *   *Example:* "On-chain proof verification in the `Verifier.sol` contract prevents a malicious prover from forging a proof and stealing funds."
*   **`source_of_truth`**: Where is this information documented? If not documented, state it explicitly.
    *   `"documented_in": ["01_SPEC.json#trusted_entities-001"]`
    *   `"documented_in": ["UNCLEAR: Not specified in documentation. Inferred from code and operational common sense."]`

--- 

## 3) Output Format (JSON)

**File:** `security-agent/outputs/01b_TRUSTMODEL.json`

Generate a valid JSON object with the following structure. Populate the `actors` and `components` arrays based on your analysis. **If information is not available in the provided documentation, you MUST mark the relevant fields as `UNCLEAR` and provide a justification in the `notes` field.** Do not invent assumptions.

```json
{
  "metadata": {
    "project_name": "zERC20", // From 01_SPEC.json
    "model_generated_at": "2025-10-29T09:00:00Z",
    "sources": [
      {
        "title": "Project Specification",
        "path": "security-agent/outputs/01_SPEC.json"
      },
      {
        "title": "Architecture Document",
        "path": "docs/architecture.md"
      }
    ]
  },
  "actors": [
    {
      "id": "ACTOR-OFFCHAIN-INDEXER",
      "name": "Off-Chain Indexer",
      "description": "Scans on-chain events and builds the off-chain Merkle tree used for withdrawal proofs.",
      "operational_scenarios": [
        {
          "scenario_id": "SCENARIO-INDEXER-CENTRALIZED",
          "description": "The indexer is run by the core protocol team.",
          "trust_level": "Semi-Trusted",
          "notes": "Trusted for liveness, but not for safety. On-chain verification mitigates malicious actions."
        },
        {
          "scenario_id": "SCENARIO-INDEXER-PERMISSIONLESS",
          "description": "Anyone can run an indexer node.",
          "trust_level": "Untrusted",
          "notes": "Documented in overview.md. The system must be safe even if all indexers are malicious."
        }
      ],
      "capabilities_if_honest": [
        "Read all `IndexedTransfer` events from the zERC20 contract.",
        "Construct a Poseidon Merkle tree from the event data.",
        "Submit IVC proofs for Merkle root updates to the Verifier contract."
      ],
      "capabilities_if_malicious": [
        "Censor specific transactions by omitting them from the tree (liveness attack).",
        "Delay or refuse to submit root proofs (liveness attack).",
        "Provide incorrect Merkle paths to users (will cause user-side proof generation to fail)." 
      ],
      "mitigations": [
        "On-chain proof verification in `Verifier.sol` ensures that only valid root transitions are accepted, regardless of the indexer's actions.",
        "The permissionless nature allows users to run their own indexer if they suspect censorship.",
        "The worst-case impact is a liveness failure, not a safety failure (funds cannot be stolen)."
      ],
      "source_of_truth": {
        "documented_in": ["overview.md#L74"],
        "notes": "The 'permissionless' nature is mentioned, but the full adversary model is not explicitly documented. The capabilities have been inferred."
      }
    }
    // ... other actors
  ],
  "components": [
      {
        "id": "COMP-ONCHAIN-VERIFIER",
        "name": "Verifier.sol",
        "description": "On-chain contract that verifies ZK proofs for withdrawals and root updates.",
        "trust_assumption": "The cryptographic primitives (Nova, Groth16) and their implementation in the contract are assumed to be secure. A flaw here would be critical.",
        "interacts_with": ["ACTOR-OFFCHAIN-INDEXER", "ACTOR-USER", "COMP-ONCHAIN-HUB"],
        "source_of_truth": {
            "documented_in": ["contract_spec.md#L17"]
        }
      }
      // ... other components
  ],
  "summary": {
      "key_assumptions": [
          "The underlying ZK proof system (Sonobe/Nova) is cryptographically sound.",
          "The LayerZero messaging layer is trusted to deliver messages from the specified remote endpoint, but the content of the messages is verified by the receiving contract.",
          "The contract owner is trusted not to upgrade contracts to a malicious implementation."
      ],
      "unclear_areas": [
          "The operational model for the Decider-Prover service is not documented. It is unclear who runs it and what the liveness assumptions are.",
          "The process for the initial trusted setup for Groth16 parameters is not specified."
      ]
  }
}
```
