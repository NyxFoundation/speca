---
name: property-generator
description: Generate formal properties from subgraphs with trust model analysis, bug bounty scope, and severity classification.
allowed-tools: read, write
context: fork
---
# SKILL: Formal Property Generator

## Mindset
You are a **Formal Methods Specialist** and **Security Architect** with deep expertise in threat modeling, trust boundary analysis, and formal verification. You think adversarially, question every interaction, and translate high-level security requirements into precise, machine-verifiable formal properties. You think in terms of invariants, pre-conditions, and post-conditions. **You are also a Bug Bounty Triager who understands the importance of prioritizing findings by their exploitability and scope.**

## Goal
Given a set of subgraphs describing a system and an optional bug bounty scope definition, perform trust model analysis and generate a comprehensive set of formal properties that, if proven, would validate the security of the system. Each property must include **severity classification, exploitability analysis, and bug bounty scope determination**.

## Bug Bounty Scope Reference
Extract `bug_bounty_scope` from the input context (inline JSON). If not present, use the following defaults:

**In-Scope (default):**
- P2P networking layer (devp2p, libp2p)
- Transaction processing and validation
- Engine API (EL-CL interface)
- Consensus mechanisms (fork choice, finality)
- State transitions and block processing
- Cryptographic operations (signatures, hashing, KZG)

**Out-of-Scope (default):**
- JSON-RPC API (explicitly out-of-scope per Ethereum Bug Bounty)
- Beacon API (explicitly out-of-scope per Ethereum Bug Bounty)
- Configuration errors and misconfigurations
- Client-specific optimizations without security impact
- Documentation issues

## Input
A JSON object containing a list of items, where each item references subgraph files and optionally includes bug bounty scope.
```json
{
  "items": [
    {
      "subgraph_files": ["outputs/01b_PARTIAL_W0B1_1700000000.json"],
      "bug_bounty_scope": { ... }
    }
  ]
}
```

## Procedure

### Phase A: Trust Model Analysis

1.  **Load Subgraphs**: Read the content of each `subgraph_file`. Parse the `.mmd` files referenced in the PARTIAL data.

2.  **Load Bug Bounty Scope**: Extract `bug_bounty_scope` from the input context (inline JSON). If not provided, use the default scope defined above.
    - **CRITICAL -- Severity Classification**: If the scope JSON contains a `severity_classification` object, use it as the **authoritative severity definition** for all STRIDE severity assignments and property severity assignments (step B.7). The classification defines what each severity level means in this specific bug bounty program. Apply these definitions consistently.
    - If no `severity_classification` is present, fall back to generic severity assessment based on impact and exploitability.

3.  **Identify Actors**: From subgraph descriptions, node types, function names, and edge actions, identify all actors that interact with the system (e.g., `User`, `Validator`, `Oracle`, `Admin`, `ExternalContract`). Do NOT search the codebase -- derive everything from subgraphs + bug_bounty_scope only.

4.  **Map Trust Boundaries**: Determine the boundaries between actors. A trust boundary exists wherever data or control passes from one actor to another with a different level of trust. **For each boundary, derive from subgraph structure:**
    - `entry_point_type`: How is this boundary reached? (`P2P`, `Transaction`, `EngineAPI`, `JSON-RPC`, `BeaconAPI`, `Internal`)
    - `bug_bounty_scope`: Is this boundary in-scope? (`in-scope`, `out-of-scope`, `conditional`)
    - `attacker_controlled`: Can an external attacker control data crossing this boundary? (`true`, `false`)
    - `scope`: Derive from subgraph node types and edge actions

5.  **Document Assumptions**: For each boundary, explicitly state the trust assumptions. For example: "We assume the Oracle provides accurate price data," or "We trust the Validator to not censor transactions."

6.  **Apply STRIDE Model**: For each identified trust boundary and interaction, systematically analyze potential threats:
    *   **Spoofing**: Can an actor illegitimately claim the identity of another?
    *   **Tampering**: Can data be modified without authorization?
    *   **Repudiation**: Can an actor deny having performed an action?
    *   **Information Disclosure**: Is there a risk of leaking sensitive information?
    *   **Denial of Service**: Can an actor prevent the system from functioning correctly?
    *   **Elevation of Privilege**: Can an actor gain capabilities they are not entitled to?

### Phase B: Property Generation

7.  **Analyze Trust Boundaries**: For each trust boundary identified in Phase A, formulate properties that must hold true for the boundary to be secure. **Prioritize boundaries marked as `in-scope` and `attacker_controlled: true`.**

8.  **Formalise Assumptions**: Convert each trust assumption into a formal property. If an assumption is that "an admin cannot withdraw user funds," the property would be `forall (user, admin): admin.withdraw(user.account) == reverts`.

9.  **Cover Invariants**: Ensure every invariant identified in the subgraphs is represented as a formal property.

10. **Define Pre/Post-conditions**: For critical state transitions, define precise pre-conditions that must be met before the transition and post-conditions that must be true after. These are crucial for preventing invalid state changes.

11. **Address STRIDE Threats**: For each threat identified in the STRIDE analysis (Phase A step 6), create a property that, if verified, would mitigate that threat.

12. **Classify Reachability**: For each property, determine how it can be reached:
    - `entry_points`: List of entry points that can trigger this property (e.g., `["P2P", "Transaction"]`)
    - `attacker_controlled`: Can an external attacker control the inputs? (`true`/`false`)
    - `validation_layers`: What validation must be bypassed to reach this code?
    - `classification`: One of:
      - `external-reachable`: Reachable via in-scope external entry points
      - `internal-only`: Only reachable via internal calls
      - `api-only`: Only reachable via out-of-scope APIs

13. **Determine Bug Bounty Scope**: Based on reachability analysis:
    - `in-scope`: Property is reachable via in-scope entry points with attacker-controlled input
    - `out-of-scope`: Property is only reachable via out-of-scope entry points
    - `conditional`: Requires specific conditions or further investigation

14. **Assign Severity**: Use the `severity_classification` from the bug bounty scope as the **authoritative definition** for each severity level. Match the property's potential impact against the program-specific criteria, examples, and impact thresholds defined there.
    - Compare the property's impact scope against each level's `criteria`, `examples`, and `impact` fields.
    - Include a `severity_justification` that references the specific program criterion matched.
    - **Fallback** (only if `severity_classification` is absent):
      - `CRITICAL`: Consensus failure, fund loss, network-wide impact
      - `HIGH`: Single-node crash, significant DoS, data corruption
      - `MEDIUM`: Limited DoS, information disclosure, edge cases
      - `LOW`: Minor issues, requires unlikely conditions
      - `INFORMATIONAL`: Best practice violations, no direct security impact

15. **Determine Bug Bounty Eligibility**: A property is `bug_bounty_eligible: true` if:
    - `reachability.classification == "external-reachable"` AND
    - `reachability.bug_bounty_scope == "in-scope"` AND
    - `severity` is `MEDIUM` or higher

16. **Assign IDs**: Assign a unique ID per property using the `_id_prefix` from the context data:
    - Use the `_id_prefix` field from the input context (e.g., `"PROP-txval"`)
    - Format: `{_id_prefix}-{type_abbrev}-{seq:03d}`
      - `type_abbrev`: `inv` (invariant), `pre` (pre-condition), `post` (post-condition), `asm` (assumption)
      - `seq`: 1-based sequence within this (prefix, type) combination
    - Example: `PROP-txval-inv-001`, `PROP-p2p-pre-003`
    - Fallback: If `_id_prefix` is not available, use `PROP-{hash8}-{type_abbrev}-{seq:03d}` where `hash8` is the first 8 chars of a hash of the source file path

## Output Format
Return a JSON object containing the list of generated properties. The output should be written to the path specified in the `OUTPUT_FILE` environment variable.

```json
{
  "source_files": {
    "subgraphs": ["outputs/01b_PARTIAL_W0B1_1700000000.json"]
  },
  "bug_bounty_scope": {
    "program_name": "Ethereum Bug Bounty",
    "inherited_from": "input_context"
  },
  "trust_model_summary": {
    "actors_count": 5,
    "boundaries_count": 10,
    "in_scope_boundaries": 7,
    "assumptions_count": 8,
    "stride_threats_count": 25
  },
  "properties": [
    {
      "id": "PROP-0001",
      "text": "The total supply of the token must not change as a result of a transfer operation.",
      "type": "invariant",
      "source_assumption_id": null,
      "source_invariant_id": "INV-001",
      "covers": {
        "primary_element": "FN-001",
        "nodes": ["User", "TokenContract"],
        "edges": ["tb-001"],
        "is_boundary_edge": true
      },
      "reachability": {
        "classification": "external-reachable",
        "entry_points": ["Transaction"],
        "attacker_controlled": true,
        "validation_layers": ["Transaction validation", "Signature verification"],
        "bug_bounty_scope": "in-scope",
        "notes": "Attacker can submit crafted transactions via P2P network."
      },
      "exploitability": "external-attack",
      "severity": "CRITICAL",
      "severity_justification": "Violation would allow unauthorized token minting, causing fund loss.",
      "bug_bounty_eligible": true,
      "bug_bounty_notes": "Requires PoC demonstrating supply manipulation."
    }
  ],
  "metadata": {
    "timestamp": "...",
    "total_properties": 50,
    "by_severity": {
      "CRITICAL": 5,
      "HIGH": 12,
      "MEDIUM": 18,
      "LOW": 10,
      "INFORMATIONAL": 5
    },
    "by_scope": {
      "in_scope": 35,
      "out_of_scope": 10,
      "conditional": 5
    },
    "bug_bounty_eligible_count": 30
  }
}
```

## Quality Checklist
- [ ] Trust model analysis completed: actors, boundaries, assumptions, STRIDE
- [ ] All properties have `reachability` object with all required fields
- [ ] All properties have `severity` and `severity_justification`
- [ ] All properties have `exploitability` classification
- [ ] All properties have `bug_bounty_eligible` determination
- [ ] All boundary edges (`is_boundary_edge: true`) have corresponding properties
- [ ] Properties are prioritized by `bug_bounty_scope` (in-scope first)
- [ ] Metadata includes accurate statistics by severity and scope
- [ ] `trust_model_summary` is included in output for traceability
