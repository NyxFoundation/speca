---
name: formal-audit
description: Perform a rigorous three-phase formal static audit on code. Use when auditing checklist items for vulnerabilities.
allowed-tools: Read, Grep, Glob, Write
context: fork
---

# SKILL: Formal Static Audit

**Description**: For a given code scope and checklist item, perform a rigorous, three-phase formal static audit to either prove the existence of a vulnerability or prove its absence, without executing code.

**Author**: Manus AI

---

## Goal

Adopt a series of expert mindsets to perform a formal static audit. The audit consists of three sequential phases: Abstract Interpretation, Symbolic Execution (including Reachability Analysis), and Invariant Proving. The final output must be a structured JSON object detailing the findings from each phase.

## Input

A JSON object representing a single audit item, with the following structure:

```json
{
  "check_id": "...",
  "checklist_item": { ... }, // The full checklist item object
  "code_scope": {
    "file": "...",
    "function": "...",
    "line_range": "..."
  }
}
```

## Execution Logic: Three-Phase Formal Audit

For the identified **Code Scope**, perform the following three phases sequentially.

### Phase 1: Abstract Interpretation

*   **Mindset**: You are an **Abstract Interpretation Specialist**. Your goal is to understand the possible states of all variables without considering specific execution paths. You think in terms of ranges, sets, and potential states.

*   **Procedure**:
    1.  Identify all variables within the Code Scope.
    2.  For each variable, determine its abstract domain (e.g., integer range `[0, 256]`, a set of possible string values).
    3.  Trace how operations within the code transform these abstract domains.
    4.  Look for potential anomalies: Can an integer overflow its range? Can a variable become null? Can a list grow unbounded?

*   **Output (Phase 1)**: A summary of the abstract state analysis, highlighting any potential state-space anomalies.

### Phase 2: Symbolic Execution & Reachability Analysis

*   **Mindset**: You are a **Symbolic Execution Engineer** and **Attack Surface Analyst**. Your goal is to find a concrete, reachable path through the code that violates the property.

*   **Procedure**:
    1.  Treat all inputs to the Code Scope as symbolic variables.
    2.  Traverse the code's control flow graph to find a set of path conditions that, when combined with the negation of the original property's assertion, are satisfiable.
    3.  If a satisfying assignment is found, you have a **counterexample**. Provide the concrete input values.
    4.  **Reachability**: Trace the data flow from external entry points (P2P, RPC, etc.) to the Code Scope. Determine if the symbolic variables in the counterexample can be controlled by an attacker.
    5.  Classify exploitability: `exploitable`, `defense-in-depth`, `internal-only`, or `unreachable`.

*   **Output (Phase 2 & 2.5)**: A list of attempted paths, the counterexample if found, and a full reachability analysis report.

### Phase 3: Invariant Proving & Bug Bounty Triage

*   **Mindset**: You are a **Theorem Proving Specialist** and **Bug Bounty Triager**. Your goal is to mathematically prove the property holds, or, if a vulnerability was found, determine its bounty eligibility.

*   **Procedure**:
    1.  If no counterexample was found, attempt to construct a formal proof that the property's assertion holds true for all paths. Identify strong guard conditions that enforce the invariant.
    2.  If a counterexample was found, use the provided Bug Bounty Scope and the reachability analysis to determine if the finding is eligible.
    3.  Check for other out-of-scope conditions (API scope, misconfiguration, etc.).

*   **Output (Phase 3 & 3.5)**: A summary of the proof attempt or a scope filtering report with the final eligibility decision.

## Output Format

Produce a single JSON object for the audited item with the structure defined in the original `prompts/03_auditmap_worker.md` (lines 192-245). This object must include `check_id`, `property_id`, `code_scope`, `final_classification`, `bug_bounty_eligible`, `summary`, and a full `audit_trail` containing the results of all phases.
