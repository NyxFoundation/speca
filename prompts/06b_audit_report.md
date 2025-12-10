


---
Description: Generic Security Audit Report Generator
Usage: `/07_audit_report [BRANCH=...] [COMMIT=...] [OUTPUT_PATH=...]`
Example: `/07_audit_report BRANCH="main" COMMIT="abc1234" OUTPUT_PATH="outputs/AUDIT_REPORT.md"`
Arguments:
- **$BRANCH**      : Target branch name (default: `main`)
- **$COMMIT**      : Target commit hash (default: current HEAD)
- **$OUTPUT_PATH** : Output file path (default: `outputs/AUDIT_REPORT.md`)
---

Generate a publication-ready **security audit report** that can apply to any project scoped in the repository outputs, without leaking repository-specific identifiers.


**Always use /serena for development tasks to keep the workflow efficient.**

# 🎯 Goal

Create a professional report that:
1. Synthesizes system intent, assets, invariants, and operating assumptions from `security-agent/outputs/01_SPEC.json` (formal specification) and `security-agent/outputs/01_PROP.json` (proposal/scope).
2. Incorporates evidence from every other available output file (e.g., `02_CHECKLIST.json`, `03_AUDITMAP.json`, `03b_FUZZING_RESULTS.json`, remediation logs) as needed to build each section.
3. Distinguishes clearly between implementation **Vulnerabilities**, specification **Gaps**, and intentional **Design Decisions**.
4. Provides actionable remediation guidance, operational recommendations, and re-verification conclusions.
5. Produces narrative text that stands on its own—someone reading only the report should understand the context without seeing raw repository names, file paths, or IDs.

# 🚫 Repository-Internal Names Are Forbidden

- **Never** include the repository name (`security-agent`), directory paths, filenames, class names, spec IDs, vulnerability IDs, or commit hashes directly from the repo outputs.
- Derive **plain-language labels** instead. Example: replace `VULN-007` with `Finding-03` or `Critical Finding 3` and phrase components as “Shielded Transfer Contract” instead of `contracts/src/ShieldedTransfer.sol`.
- When code evidence is necessary, paraphrase logic or rename identifiers to descriptive placeholders (`VerifierRoutine`, `MerkleUpdater`). Only include short excerpts after sanitizing identifiers.
- Ensure every table, heading, or bullet uses normalized labels generated during report creation (e.g., sequential numbering) instead of raw IDs from `03_AUDITMAP.json` or other outputs.
- Do not cite repository paths or configuration filenames in the final report. Describe environments generically (“Rust prover workspace”, “Solidity contracts suite”).

# 📥 Auto-load Data Sources

## 1. Specification & Product Context
- Load `security-agent/outputs/01_SPEC.json` for canonical requirements, invariants, trust assumptions, actor roles, and network targets.
- Load `security-agent/outputs/01_PROP.json` for scope, objectives, deliverables, milestones, and stakeholder expectations.
- Extract descriptions of assets, modules, workflows, cryptographic constraints, and operational procedures. Convert any identifiers into narrative names before use.

## 2. Repository Metadata & Build Context
- If `$COMMIT` not provided, read `.git/HEAD` to resolve the active commit.
- Detect languages/toolchains by scanning for standard config files (e.g., `foundry.toml`, `hardhat.config.*`, `Cargo.toml`, `package.json`). Reference them generically (“Solidity toolchain configuration”) rather than citing filenames in the report.
- Collect branch information, audit period (based on git log), and contributor roles for document control.

## 3. Audit Findings
- Load `security-agent/outputs/03_AUDITMAP.json` and collect every `audit_items[]` entry.
- For each entry, record severity, category, affected component summary, remediation status, and any `dynamic_test` metadata.
- Map findings back to specification requirements extracted from `01_SPEC.json` / `01_PROP.json` (or other outputs) to justify Vulnerability vs. Spec-gap classifications.
- When generating report references, **relabel** each finding with fresh sequential handles (e.g., `Finding-01`, `Gap-02`). Maintain an internal map to original IDs for consistency, but never expose raw IDs in the final text.

## 4. Dynamic & Automated Testing
- Load `security-agent/outputs/03b_FUZZING_RESULTS.json` and correlate entries to their associated findings via `checklist_id` or related fields.
- Capture run counts, seeds (if available), failures, and test status. Describe them generically (“10,000-run fuzz campaign on withdraw circuit”) without file/test names.

## 5. Checklist Coverage
- Load `security-agent/outputs/02_CHECKLIST.json` to understand control objectives, severity hints, and evidence expectations.
- Highlight checklist items that remain untested or unresolved, again renaming any provided IDs to report-safe labels.

## 6. Other Outputs
- Inspect additional files under `security-agent/outputs/` (e.g., remediation summaries, confirmation logs) to substantiate re-verification or operational guidance.
- Integrate only the information itself—strip away filenames or IDs before publication.

# 📋 Report Structure (Mandatory)

## 0) Cover Page & Document Control
- **Title**: Use the project name stated in `01_SPEC.json` or `01_PROP.json`; if multiple names exist, choose the most user-facing label. Append “Security Assessment Report”.
- **Version**: Start at `v1.0` or increment based on prior releases.
- **Date**: Current date in `YYYY-MM-DD` format.
- **Classification**: Default to `Confidential` unless otherwise specified.
- **Audit Scope Summary**: Describe repositories, deployment targets, and audit horizon in plain language (e.g., “Shielded asset protocol contracts and proving stack”).
- **Branch & Commit**: Describe them generically (“Latest mainline commit as of 2025-11-13”); avoid listing hash or branch names unless sanitized.
- **Audit Period**: Derive from git history; express as calendar dates.
- **Auditor(s)** and **Contact**: Use organization/team names provided in outputs or default to `Audit Team`.
- **Disclaimer**: Include a standard limitation-of-liability paragraph.

## 1) Executive Summary
Use the following template but ensure all references are sanitized:

```markdown
## 1. Executive Summary

### Overall Assessment
<State deployment readiness: Ready / Conditional / Blocked>
<List key blockers if any>

### Top Critical Findings
1. **Finding-01** <Title>: <Impact> → <Status>
2. ... (limit to 5 items)

### Remediation Snapshot
- **Total Findings**: X (Critical: Y, High: Z, ...)
- **Remediation Rate**: X% (Resolved vs. outstanding)
- **Outstanding Issues**: Describe items blocking launch

### Recommendations
- <Specification updates>
- <Operational / governance actions>
- <Testing or monitoring improvements>
```

## 2) Scope Definition
- Summarize **in-scope assets** using descriptions from `01_SPEC.json` / `01_PROP.json` (e.g., “Shielded token contracts”, “Zero-knowledge proof circuits”, “Indexer and relayer services”). Avoid path references.
- List **out-of-scope components** with rationale.
- Describe **compilation and runtime environments** generically (compiler families, toolchains, networks) using data detected from config files; do not cite filenames.
- Enumerate **specification references** by title or section heading, not by file path.
- State **target networks and dependencies** (e.g., “intended for Ethereum L2 deployments with cross-chain messaging via a trusted bridge”).

## 3) System Overview & Trust Model
- Provide a textual architecture summary describing modules, data flow, trust zones, and key actors using terminology from the specification outputs.
- Highlight invariants, safety requirements, and design constraints captured in `01_SPEC.json` (range limits, Merkle depth, accounting rules, domain separation, etc.).
- Document trust boundaries and operational responsibilities without citing repository-specific names.

## 4) Methodology
- Explain the audit approach (spec review, manual code review, static analysis, property-based testing, fuzzing, formal analysis).
- Describe tooling and execution environments in generic terms (e.g., “Solidity audits executed with Foundry toolchain, property tests run with Rust-based frameworks”).
- Summarize verification evidence from `03b_FUZZING_RESULTS.json` and other outputs.
- Include a methodology template similar to the original file, but sanitize all tool/version references (e.g., “latest stable compiler release”).

## 5) Specification Traceability
- Build a matrix mapping **Requirement → Implementation Concept → Test Evidence → Finding Reference**.
- Use requirement names from `01_SPEC.json` / `01_PROP.json`, but paraphrase them so the reader does not need to see the original IDs.
- Example table (edit values accordingly):

```markdown
| Requirement Label | Source Description | Implementation Concept | Test Evidence | Finding Reference |
|-------------------|--------------------|------------------------|---------------|-------------------|
| Shielded transfer must conserve supply | Derived from Privacy Token Spec §Supply Controls | Core token logic | Supply balance fuzzing campaign | Finding-02 |
| Merkle tree depth fixed to prevent overflow | Derived from Circuit Spec §Merkle Constraints | Proof circuit for inserts | Circuit property test | Gap-01 |
```

- After the matrix, list **Spec-gaps** discovered (requirements missing from the spec) using sanitized labels.

## 6) Finding Classification Criteria
- Define categories (Vulnerability / Spec-gap / Not-a-bug) with narrative definitions.
- Define severity levels (Critical ↔ Informational) and evaluation criteria.
- Define status values (Open / Mitigated / Fixed / Accepted Risk / Duplicate) without referencing repos or commits.
- If referencing fixes, describe them as “Patched in November 2025 hotfix” rather than citing commit hashes.

## 7) Findings Summary Table
Provide a one-page overview with sanitized references:

```markdown
## 7. Findings Summary

| Reference | Title | Severity | Category | Impacted Components | Status | Remediation Notes |
|-----------|-------|----------|----------|---------------------|--------|-------------------|
| Finding-01 | Reused nullifier allows replay | Critical | Vulnerability | Privacy token core | Open | Patch pending
| Gap-02 | Missing rate-limit requirement | High | Spec-gap | Relayer policy | Accepted Risk |
| ... | ... | ... | ... | ... | ... | ... |

### Severity Breakdown
- Critical: X (Resolved Y / Open Z)
- High: ...

### Category Breakdown
- Vulnerabilities: ...
- Spec-gaps: ...
- Not-a-bugs: ...
```

## 8) Detailed Findings
For each entry in `03_AUDITMAP.json` generate a sanitized section. Template:

```markdown
### Finding-0N: <Plain-language title>
- **Severity**: Critical | High | Medium | Low | Informational
- **Category**: Vulnerability | Spec-gap | Design Decision (Not-a-bug)
- **Impacted Components**: Describe using functional names (“Shielded transfer verifier”, “Batch relayer”).
- **Status**: Open | Fixed | Mitigated | Accepted Risk
- **Summary**: 1–2 sentences describing the issue.

**Specification Context**
- Requirement summary derived from 01_SPEC/01_PROP (paraphrased).
- If Spec-gap: explicitly state “Requirement absent from governing specification; recommended addition: <MUST/SHOULD statement>”.

**Impact**
- Describe user/system harm, affected invariants, and realistic attack scenarios.

**Evidence**
- Reference sanitized logic descriptions (“The deposit validator omits uniqueness checks before updating the state”).
- If code excerpts are necessary, rename identifiers to generic placeholders before quoting.
- Mention supporting checklist/fuzzing evidence without exposing IDs (“Validated by property-based test covering 20k runs; 3 failures observed”).

**Mitigation**
- Provide actionable steps (patch summary, spec amendment, monitoring addition).

**Discussion** (optional)
- Cost/benefit analysis, alternatives, or rationale for accepted risk.
```

## 9) Re-Verification
- Document the status of remediated findings without citing commit hashes. Use descriptions like “Patched via November 2025 upgrade package”.
- Include a table of fixed items, tests added, and verification results using sanitized references.
- Summarize developer responses and auditor conclusions with neutral wording.

## 10) Operational Recommendations & Release Checklist
- Cover key management, emergency procedures, telemetry, deployment readiness, and known constraints using information extracted from outputs and spec.
- Present recommendations generically (e.g., “Introduce multi-person approval for parameter changes”) with checklists for deployment.

## 11) Appendix
- Glossary, interfaces, address lists, compilation settings, and audit scripts should be described in plain language.
- When listing interfaces or parameters, use functional titles (“Token Controller interface”) instead of filenames.
- Include sign-off / acceptance statements.

# 🛠️ Generation Workflow

```
1. Load `01_SPEC.json`, `01_PROP.json`, `02_CHECKLIST.json`, `03_AUDITMAP.json`, `03b_FUZZING_RESULTS.json`, and any other relevant `outputs/*` files.
2. Build an internal data model linking requirements, components, tests, and findings.
3. Generate sanitized labels for every finding, requirement, checklist item, and fix before drafting any section.
4. Draft each report section following the structure above, ensuring narrative explanations do not rely on repository paths or IDs.
5. Cross-check that every finding includes category, severity, impact, remediation, and (if applicable) fuzzing evidence derived from the outputs.
6. Perform a self-check: all mandatory sections present, no placeholder text remains, and no repository-specific proper nouns, file paths, IDs, or hashes appear.
7. Write the final report to `$OUTPUT_PATH`.
```

Ensure the final document can be shared independently: it must explain the system, issues, and remediation steps without exposing internal repository metadata.
