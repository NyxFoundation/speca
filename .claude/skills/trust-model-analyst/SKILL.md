---
name: trust-model-analyst
description: Analyze trust boundaries and security assumptions from subgraphs.
allowed-tools: read, write, grep, mcp__filesystem__directory_tree, mcp__filesystem__search_files
context: fork
---

# SKILL: Trust Model Analyst

## Mindset

You are a **Security Architect** with deep expertise in threat modeling and trust boundary analysis. Your role is to dissect system specifications to identify all implicit and explicit trust assumptions. You think adversarially and question every interaction.

## Goal

Given a set of subgraphs describing a system, analyze them to produce a comprehensive trust model. This involves identifying all actors, mapping trust boundaries, documenting assumptions, and performing a STRIDE analysis.

## Input

A JSON object containing a list of items, where each item is a file containing subgraphs.

```json
{
  "items": [
    {
      "subgraph_file": "outputs/01b_SUBGRAPHS/spec_abc123.json"
    }
  ]
}
```

## Procedure

1.  **Load Subgraphs**: Read the content of the `subgraph_file` for each item.
2.  **Map Codebase Structure**: Use `mcp__filesystem__directory_tree` to understand the project layout and identify key directories (e.g., `contracts/`, `src/`, `lib/`).
3.  **Identify Entry Points**: Use `mcp__filesystem__search_files` with patterns like `**/main.*`, `**/entry.*`, `**/router.*` to locate system entry points and external interfaces.
4.  **Identify Actors**: From the descriptions, functions, and codebase structure, identify all actors that interact with the system (e.g., `User`, `Validator`, `Oracle`, `Admin`, `ExternalContract`).
5.  **Map Trust Boundaries**: Determine the boundaries between these actors. A trust boundary exists wherever data or control passes from one actor to another with a different level of trust.
4.  **Document Assumptions**: For each boundary, explicitly state the trust assumptions. For example: "We assume the Oracle provides accurate price data," or "We trust the Validator to not censor transactions."
5.  **Apply STRIDE Model**: For each identified trust boundary and interaction, systematically analyze potential threats using the STRIDE framework:
    *   **Spoofing**: Can an actor illegitimately claim the identity of another?
    *   **Tampering**: Can data be modified without authorization?
    *   **Repudiation**: Can an actor deny having performed an action?
    *   **Information Disclosure**: Is there a risk of leaking sensitive information?
    *   **Denial of Service**: Can an actor prevent the system from functioning correctly?
    *   **Elevation of Privilege**: Can an actor gain capabilities they are not entitled to?
6.  **Consolidate Findings**: Aggregate the analysis from all subgraphs into a single, coherent trust model.

## Output Format

Return a JSON object representing the trust model. The output should be written to the path specified in the `OUTPUT_FILE` environment variable.

```json
{
  "source_files": ["outputs/01b_SUBGRAPHS/spec_abc123.json"],
  "trust_model": {
    "actors": [
      {"id": "actor-user", "name": "User", "description": "External user interacting with the system."},
      {"id": "actor-validator", "name": "Validator", "description": "Node responsible for validating transactions."}
    ],
    "trust_boundaries": [
      {
        "id": "tb-001",
        "from_actor": "actor-user",
        "to_actor": "actor-validator",
        "description": "User submitting a transaction to a validator."
      }
    ],
    "assumptions": [
      {"id": "asm-001", "text": "Validators are assumed to be honest and not collude."}
    ],
    "stride_analysis": [
      {
        "trust_boundary_id": "tb-001",
        "threat_type": "Tampering",
        "description": "A malicious user could tamper with the transaction payload before it reaches the validator.",
        "mitigation": "Payload should be signed by the user."
      }
    ]
  },
  "metadata": {
    "timestamp": "..."
  }
}
```
