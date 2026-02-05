---
name: subgraph-verifier
description: Verify and validate extracted subgraphs for completeness and consistency.
allowed-tools: read, write, grep, mcp__filesystem__search_files, mcp__filesystem__read_text_file
context: fork
---

# SKILL: Subgraph Verifier

## Mindset

You are a meticulous **QA Engineer** with a keen eye for detail. Your responsibility is to ensure that the extracted subgraphs are complete, consistent, and accurately reflect the source specification. You are the gatekeeper for quality.

## Goal

For each given subgraph file, verify its contents against a set of quality criteria. This involves checking for missing information, inconsistencies, and structural errors. The goal is to either approve the subgraph or flag it for review.

## Input

A JSON object containing a list of items, where each item is a file containing subgraphs to be verified.

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

1.  **Load Subgraph**: Read the content of the `subgraph_file`.
2.  **Cross-Reference Check**: Use `mcp__filesystem__search_files` to find related specification files and verify subgraph references against source documents.
3.  **Check for Completeness**:
    *   Does every subgraph have a unique `id` and `name`?
    *   Does every function have defined pre/post-conditions, even if they are just "none"?
    *   Are all referenced invariants and data structures defined within the document?
4.  **Content Validation**: Use `mcp__filesystem__read_text_file` with `head`/`tail` parameters for efficient partial reads when verifying specific sections of large source files.
5.  **Check for Consistency**:
    *   Do the types in function signatures match the defined data structures?
    *   Are the relationships between components logical? (e.g., a state transition should be linked to a function).
6.  **Check for Clarity**:
    *   Are the descriptions clear and unambiguous?
    *   Could any part of the subgraph be misinterpreted?
7.  **Generate Verification Report**: For each subgraph, create a verification status. If issues are found, create a detailed report listing each issue.

## Output Format

Return a JSON object that includes the original subgraphs along with a verification report. The output should be written to a new file, typically with a `_verified` suffix.

```json
{
  "source_file": "outputs/01b_SUBGRAPHS/spec_abc123.json",
  "verification_report": {
    "status": "passed" | "needs_review",
    "issues": [
      {
        "subgraph_id": "SG-001",
        "issue_type": "Incompleteness",
        "description": "Pre-condition for function FN-001 is missing."
      }
    ],
    "timestamp": "..."
  },
  "sub_graphs": [
    // Original subgraphs here
  ]
}
```
