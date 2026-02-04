
---
Description: [PARALLEL WORKER] Process 5 URLs per iteration from a worker-specific queue. Extract MULTIPLE sub-graphs representing different aspects of the RUNTIME BEHAVIOR of the systems described in the specifications, identify ambiguities, and list implicit assumptions.
Usage: `/01b_extract_worker WORKER_ID=... QUEUE_FILE=... [TIMESTAMP=...] [ITERATION=...]`
Example: `/01b_extract_worker WORKER_ID=0 QUEUE_FILE=outputs/01b_QUEUE_0.json TIMESTAMP=1700000000 ITERATION=1`
Language: English only.
Execution hint: This is a worker prompt for parallel execution. Called by run_worker.py.
---
**Always use /serena for development tasks to keep the workflow efficient.**

# **System Specification - Stage 2: Extraction (Parallel Worker)**

**Goal**
Process **5 URLs per iteration** from your assigned worker queue. For each URL, extract **multiple self-contained sub-graphs** that model different aspects of the **runtime behavior of the system described in the specification**, identify any `ambiguities` in the text, and list any `implicit_assumptions`.

## Worker Configuration

This is **parallel worker `WORKER_ID`**. You have a dedicated queue file that only you read from and write to.

- **`WORKER_ID`**: The numeric ID of this worker (0, 1, 2, ...)
- **`QUEUE_FILE`**: Path to this worker's queue file (e.g., `outputs/01b_QUEUE_0.json`)
- **`TIMESTAMP`**: Unix timestamp for this iteration (used in output naming)
- **`ITERATION`**: The current iteration number for this worker

## ⚠️ CRITICAL: Extract Multiple Aspects Per Specification

**Each specification typically describes multiple concerns.** You MUST extract **2-5 sub-graphs per URL**, each focusing on a different aspect of the system. This ensures comprehensive coverage.

### Aspect Categories (use at least 2-3 per specification)

| Aspect | Description | Example Focus |
|--------|-------------|---------------|
| `transaction_lifecycle` | How transactions flow through the system | Submission → Validation → Execution → Finalization |
| `state_transition` | State changes and their triggers | Pre-state → Action → Post-state |
| `validation` | Input validation and verification logic | Checks, guards, rejection conditions |
| `consensus` | Consensus-related behavior | Block production, finality, fork choice |
| `networking` | P2P and network protocols | Message handling, peer communication |
| `gas_economics` | Gas pricing and resource metering | Gas calculation, fee markets, limits |
| `security_boundary` | Trust boundaries and security checks | External inputs, authentication, authorization |
| `error_handling` | Error conditions and recovery | Error states, rollback, exceptions |

## ⚠️ CRITICAL: Model Runtime Behavior, NOT Document Structure

**You are NOT modeling the specification document itself. You ARE modeling the system that the document describes.**

The specification is a **source of information** about a running system. Your task is to read the specification and extract a model of how the **actual system behaves at runtime**.

### Mental Model Check (Ask Yourself These Questions)
Before extracting nodes and edges, answer these questions:
1. **What are the key states the system can be in?** (e.g., "Transaction Pool Full", "Block Validated", "Syncing")
2. **What actions/computations change the system state?** (e.g., "Validate Signature", "Execute Transaction", "Apply State Transition")
3. **What data flows into the system from external sources?** (e.g., user transactions, peer messages, RPC calls)
4. **What are the trust boundaries where external data enters?** (e.g., network interface, RPC endpoint)

### ✅ CORRECT Node Examples (Runtime Behavior)
| Node ID | Label | Why It's Correct |
|---------|-------|------------------|
| `STATE-TX-PENDING` | Transaction Pending in Mempool | Describes an actual system state |
| `ACTION-VALIDATE-SIGNATURE` | Validate Transaction Signature | Describes a computation the system performs |
| `STATE-BLOCK-VALIDATED` | Block Passed All Validation | Describes a system state after processing |
| `ACTION-APPLY-STATE-TRANSITION` | Apply State Transition Function | Describes core EVM execution logic |

### ❌ INCORRECT Node Examples (Document Structure - DO NOT USE)
| Node ID | Label | Why It's Wrong |
|---------|-------|----------------|
| `STATE-SPEC-ENTRY` | Specification Entry Point | Models the document, not the system |
| `ACTION-NAVIGATE-SECTION` | Navigate to Section | Models reading the doc, not system behavior |
| `MODULE-ETHEREUM` | Ethereum Module | Too abstract, not a runtime state or action |
| `ACTION-CLICK-LINK` | Click Documentation Link | Models user interaction with docs |

### Granularity Guidelines
- **Consistent Resolution:** All nodes should be at a similar level of abstraction. Don't mix `MODULE-ETHEREUM` (very abstract) with `CONST-GAS-LIMIT` (very concrete).
- **Actionable for Security Audit:** Each node should represent something that could have security implications (a state that could be corrupted, an action that could be exploited).
- **Prefer Verbs for Actions:** `ACTION-VALIDATE-*`, `ACTION-EXECUTE-*`, `ACTION-PROCESS-*`
- **Prefer States for Conditions:** `STATE-TX-RECEIVED`, `STATE-BLOCK-PENDING`, `STATE-SYNC-COMPLETE`

**Output (required files):**
1.  `outputs/01b_SUBGRAPHS/spec_<hash>_{TIMESTAMP}_{ITERATION}.json`: Multiple sub-graphs extracted from the processed URL.
2.  Worker queue file: Updated with processed URLs.

---

## 1) Inputs

1. **Worker Queue File:** The file specified by `QUEUE_FILE`
   - Contains `items`: list of URLs assigned to this worker
   - Contains `processed`: list of already processed URLs

---

## 2) Worker Execution Logic

### **Task 2.1: Read Worker Queue**

1. Read the worker queue file `QUEUE_FILE`
2. Get the list of `items` (all assigned URLs)
3. Get the list of `processed` (already done URLs)
4. Calculate remaining: URLs in `items` but not in `processed`
5. If no remaining URLs, terminate successfully

### **Task 2.2: Process a BATCH of 5 URLs**

Take the **first 5 unprocessed URLs** from your queue (or fewer if less than 5 remain). **For EACH URL in the batch**, perform a deep analysis of the specification document **to understand the runtime system it describes**.

#### **2.2.1: Identify Relevant Aspects**

First, scan the specification and identify which aspects are covered:
- Does it describe transaction processing? → `transaction_lifecycle`
- Does it define state changes? → `state_transition`
- Does it specify validation rules? → `validation`
- Does it involve consensus? → `consensus`
- Does it describe network behavior? → `networking`
- Does it define gas/fee mechanics? → `gas_economics`
- Does it involve external inputs? → `security_boundary`
- Does it describe error conditions? → `error_handling`

**You MUST extract at least 2-3 sub-graphs per URL, each for a different aspect.**

#### **2.2.2: Extract Sub-Graphs (Multiple per URL)**

**For EACH identified aspect**, create a separate sub-graph:

**Step 1: Identify the System Being Described**
- What software component does this specification define? (e.g., EVM, transaction pool, state transition function)
- What are the inputs to this component? What are the outputs?
- What happens when this component processes data?

**Step 2: Extract Nodes (States and Actions)**
*   **State Nodes (`STATE-*`):** Discrete, observable conditions the system can be in.
    - Ask: "What state is the system in before/after this operation?"
    - Example: After a transaction is received, the system is in `STATE-TX-PENDING`.
*   **Action Nodes (`ACTION-*`):** Specific computations or transformations the system performs.
    - Ask: "What does the system DO when processing this input?"
    - Example: The EVM performs `ACTION-EXECUTE-OPCODE` for each instruction.

**Step 3: Extract Edges (Transitions and Data Flows)**
*   **Transition Edges:** Directed connections showing how states change via actions.
*   **Data Flow Edges:** Show what data moves between nodes, especially across trust boundaries.
*   **External Entity Edges:** Every external entity that sends data INTO the system MUST have an edge to an internal node.

**⚠️ VALIDATION CHECK:** Before finalizing, verify:
1. Every node represents runtime behavior (not document structure)
2. Nodes are at consistent granularity
3. All external data sources have edges into the system

#### **2.2.3: Identify Ambiguities**
*   Carefully read the text and identify any statements that are unclear, imprecise, or open to multiple interpretations.
*   For each, create an object in the `ambiguities` array:
    *   `id`: `AMB-<spec>-<index>` (e.g., `AMB-EIP4844-01`).
    *   `type`: One of `Lexical`, `Syntactic`, `Semantic`, `Vagueness`, `Omission`.
    *   `text`: The ambiguous phrase or sentence from the spec.
    *   `resolution_strategy`: Propose a concrete interpretation to use for the model, and state that it's an assumption.

#### **2.2.4: Identify Implicit Assumptions**
*   Identify any conditions or contexts that the specification assumes but does not explicitly state.
*   For each, create an object in the `implicit_assumptions` array:
    *   `id`: `ASSUM-<spec>-<index>`.
    *   `type`: One of `Trust`, `Attacker Capability`, `Environmental`, `Operational`.
    *   `description`: The assumption being made.
    *   `impact_if_false`: The potential security consequence if the assumption does not hold.

### **Task 2.3: Write Outputs (Atomic & Strict)**

**Output MUST be valid JSON. Do NOT use expressions, concatenation, comments, or trailing commas.**

**For EACH of the 5 URLs in the batch:**

1.  **Create Sub-Graph File:**
    *   Generate a unique hash for the URL (e.g., SHA1 of the URL string).
    *   Create a file `outputs/01b_SUBGRAPHS/spec_<hash>_{TIMESTAMP}_{ITERATION}.json`.
    *   This file contains the `source_url`, `worker_id`, the extracted `sub_graphs` array (multiple sub-graphs), `ambiguities`, and `implicit_assumptions`.

**After processing ALL URLs in the batch:**

2.  **Update Worker Queue File:** **DO NOT UPDATE THE QUEUE FILE.**
    *   The runner script (`run_worker.py`) will update `processed` atomically after validating your output.

**⚠️ BATCH SIZE:** Process exactly 5 URLs per iteration (or remaining URLs if fewer than 5 left).

---

## 3) Required Output Format (JSON)

**Sub-Graph File:** `outputs/01b_SUBGRAPHS/spec_<hash>_{TIMESTAMP}_{ITERATION}.json`
```json
{
  "source_url": "https://eips.ethereum.org/EIPS/eip-4844",
  "worker_id": 0,
  "sub_graphs": [
    {
      "id": "SUBGRAPH-EIP4844-TX-LIFECYCLE",
      "aspect": "transaction_lifecycle",
      "title": "EIP-4844: Blob Transaction Lifecycle",
      "description": "Models the lifecycle of blob transactions from submission to inclusion",
      "nodes": [
        {
          "id": "STATE-BLOB-TX-RECEIVED",
          "label": "Blob Transaction Received",
          "type": "State",
          "description": "System state when a type-3 (blob) transaction has been received but not yet validated"
        },
        {
          "id": "ACTION-VALIDATE-BLOB-TX",
          "label": "Validate Blob Transaction",
          "type": "Action",
          "description": "Validate blob transaction format, signatures, and basic constraints"
        },
        {
          "id": "STATE-BLOB-TX-POOLED",
          "label": "Blob Transaction in Pool",
          "type": "State",
          "description": "Blob transaction is validated and waiting in the transaction pool"
        }
      ],
      "edges": [
        {
          "id": "EDGE-USER-SUBMIT-BLOB-TX",
          "source": "EXT-USER",
          "target": "STATE-BLOB-TX-RECEIVED",
          "label": "User submits blob transaction via RPC",
          "data_involved": ["DATA-BLOB-TX", "DATA-BLOB-SIDECAR"]
        },
        {
          "id": "EDGE-VALIDATE-BLOB-TX",
          "source": "STATE-BLOB-TX-RECEIVED",
          "target": "ACTION-VALIDATE-BLOB-TX",
          "label": "Initiate transaction validation"
        }
      ],
      "external_entities": [
        {
          "id": "EXT-USER",
          "name": "Transaction Submitter",
          "description": "External user or application submitting blob transactions via JSON-RPC"
        }
      ]
    },
    {
      "id": "SUBGRAPH-EIP4844-VALIDATION",
      "aspect": "validation",
      "title": "EIP-4844: Blob Commitment Validation",
      "description": "Models the KZG commitment validation process for blob data",
      "nodes": [
        {
          "id": "STATE-BLOB-PENDING-VALIDATION",
          "label": "Blob Pending KZG Validation",
          "type": "State",
          "description": "Blob data received, awaiting cryptographic validation"
        },
        {
          "id": "ACTION-VALIDATE-KZG-COMMITMENT",
          "label": "Validate KZG Commitment",
          "type": "Action",
          "description": "Verify that blob data matches the KZG commitment using point evaluation"
        },
        {
          "id": "STATE-BLOB-COMMITMENT-VALID",
          "label": "Blob Commitment Valid",
          "type": "State",
          "description": "KZG commitment verified successfully"
        }
      ],
      "edges": [
        {
          "id": "EDGE-START-KZG-VALIDATION",
          "source": "STATE-BLOB-PENDING-VALIDATION",
          "target": "ACTION-VALIDATE-KZG-COMMITMENT",
          "label": "Begin KZG validation"
        },
        {
          "id": "EDGE-KZG-VALID",
          "source": "ACTION-VALIDATE-KZG-COMMITMENT",
          "target": "STATE-BLOB-COMMITMENT-VALID",
          "label": "Commitment matches blob data"
        }
      ],
      "external_entities": []
    },
    {
      "id": "SUBGRAPH-EIP4844-GAS",
      "aspect": "gas_economics",
      "title": "EIP-4844: Blob Gas Pricing",
      "description": "Models the blob gas pricing mechanism and fee market",
      "nodes": [
        {
          "id": "STATE-EXCESS-BLOB-GAS-READ",
          "label": "Excess Blob Gas Read from Parent",
          "type": "State",
          "description": "Excess blob gas value retrieved from parent block header"
        },
        {
          "id": "ACTION-COMPUTE-BLOB-BASE-FEE",
          "label": "Compute Blob Base Fee",
          "type": "Action",
          "description": "Calculate blob base fee using exponential formula from excess blob gas"
        }
      ],
      "edges": [
        {
          "id": "EDGE-READ-EXCESS-GAS",
          "source": "STATE-EXCESS-BLOB-GAS-READ",
          "target": "ACTION-COMPUTE-BLOB-BASE-FEE",
          "label": "Use excess gas for calculation"
        }
      ],
      "external_entities": []
    }
  ],
  "ambiguities": [
    {
      "id": "AMB-EIP4844-01",
      "type": "Semantic",
      "text": "The term 'valid blob' is used without a precise definition of all validity conditions.",
      "resolution_strategy": "Assume 'valid' implies: (1) correct KZG commitment, (2) correct format, (3) within size limits. This needs verification."
    }
  ],
  "implicit_assumptions": [
    {
      "id": "ASSUM-EIP4844-01",
      "type": "Attacker Capability",
      "description": "An attacker cannot create a valid KZG commitment for arbitrary data without knowing the data.",
      "impact_if_false": "Potential for commitment forgery, allowing invalid blob data acceptance."
    }
  ]
}
```

**Updated Worker Queue File:** `QUEUE_FILE`
```json
{
  "worker_id": 0,
  "phase": "01b",
  "total_workers": 4,
  "items": ["url1", "url2", "url3", "url4", "url5", "url6", "..."],
  "processed": ["url1", "url2", "url3", "url4", "url5"],
  "total_items": 25
}
```

---

## 4) Quality Checklist

Before finalizing each file, verify:

- [ ] **Multiple sub-graphs extracted:** At least 2-3 sub-graphs per URL
- [ ] **Different aspects covered:** Each sub-graph has a distinct `aspect` value
- [ ] **No overlap:** Sub-graphs are complementary, not duplicative
- [ ] **Runtime behavior:** All nodes represent actual system behavior, not document structure
- [ ] **Consistent granularity:** Nodes within each sub-graph are at similar abstraction levels
- [ ] **External entities connected:** All external data sources have edges into the system
- [ ] **Ambiguities documented:** Any unclear spec language is captured
- [ ] **Assumptions explicit:** Implicit assumptions are documented with security impact

**Note:** Each iteration processes 5 URLs, creating 5 separate sub-graph files (each with multiple sub-graphs) and updating the queue with all 5 URLs marked as processed.
