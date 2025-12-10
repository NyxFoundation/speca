


---
Description: Bug-Bounty Report Builder
Usage: `/06_report VULN_ID=... REPORT_TYPE=... [SEVERITY=...]`
Example: `/06_report VULN_ID="0023344" REPORT_TYPE="ETHEREUM" SEVERITY="critical"`
Arguments:
- **$VULN_ID**         : `audit_items[].id` in `03_AUDITMAP.json`
- **$REPORT_TYPE**     : One of `CANTINA`, `CODE4RENA`, `ETHEREUM`, `IMMUNEFI`, `SHERLOCK`
- **$SEVERITY**        : Optional override (e.g. `critical`, `high`, `medium`, `low`)
---

Generate a complete **Markdown bug-bounty report** tailored to the selected bounty program.

**Always use /serena for these development tasks to maximize token efficiency:**


# 📥 Auto-load from 03_AUDITMAP.json
1. **Read** `security-agent/outputs/03_AUDITMAP.json`.
2. **Locate** the entry where `audit_items[].id == $VULN_ID`.
3. **Extract**
   - `SNIPPET`        <- `audit_items[].snippet`
   - `SRC_FILE`       <- `audit_items[].file`
   - `SRC_FUNCTION`   <- infer the enclosing function or method name (fallback: short descriptive label)
   - `UT_PATH`        <- first `poc_tests[].file` with `"type": "unit"`
   - `IT_PATH`        <- first `integration_tests[].file` (if any)
   - `VULN_TITLE_RAW` <- `audit_items[].description`
   - `VULN_TITLE`     <- text before the first colon (`:`) in `VULN_TITLE_RAW`, or the full string if no colon exists. If empty, craft a concise fallback title without embedding `$VULN_ID`.
   - `TITLE_SLUG`     <- `VULN_TITLE` transformed to lowercase snake_case containing only ASCII letters, digits, and underscores (convert spaces/punctuation to underscores, collapse repeats, strip leading/trailing underscores). If the slug length exceeds 40 characters, remove filler words or truncate cleanly so the final slug ≤ 40 characters.
4. **If not found** → abort with
   `"Vulnerability '$VULN_ID' not found in 03_AUDITMAP.json"`.
5. **Resolve template** → map `$REPORT_TYPE` to `security-agent/docs/report_templates/{{REPORT_TYPE}}.md`; abort if the file does not exist.

# 🎯 Goal
1. **Read** `security-agent/docs/report_templete_{{REPORT_TYPE}}.md` for the selected `$REPORT_TYPE` and fill *all* placeholders while preserving heading order and stylistic expectations.
2. Use internal data sources (Ethereum specs, audit map, bounty rules) strictly for authoring context—never surface repository paths or filenames in the final report.
   - Pull from `security-agent/docs/ethereum/spec_*`, `security-agent/outputs/01_SPEC.json`, and `security-agent/outputs/03_AUDITMAP.json` as needed, but redact those identifiers from the deliverable.
   - When `$SEVERITY` is omitted, consult `security-agent/outputs/01_BOUNTY_GUIDELINE.md` to derive a justified classification.
   - Strip or rewrite any internal markers (e.g. `AP`, `SR`, `NORMATIVE_ID`, `@audit`, `@audit-ok`) so the public report contains only neutral wording.
3. Embed **verbatim PoC code** from sanitized sources:
   - Unit test → `{{UT_PATH}}`
   - Integration test → `{{IT_PATH}}` (if present)
   Provide human-friendly labels and run commands that omit `security-agent/` prefixes or other repository-only context, explicitly including the test file path(s) and exact command(s) needed to execute them.

# 📤 Output
Write exactly **one Markdown file**:
`security-agent/outputs/report_{{TITLE_SLUG}}.md`
(no extra headings, no missing sections).
Ensure the filename component `report_{{TITLE_SLUG}}.md` stays ≤ 55 characters; reduce the slug length further if necessary before writing.

# 📝 Mandatory Sections

Must Follow template

# 🛠️ Generation Workflow
```
1. Resolve `$REPORT_TYPE` → load `security-agent/docs/report_templates/{{REPORT_TYPE}}.md` and collect placeholders like {{SEVERITY}}, {{POC}}.
2. Determine severity: if `$SEVERITY` argument is present, normalise and apply it; otherwise compute Impact × Likelihood using `security-agent/outputs/01_BOUNTY_GUIDELINE.md` and record the rationale internally.
3. Read PoC files (UT_PATH and IT_PATH) and include in fenced code blocks, ensuring each snippet is accompanied by the file path and explicit test command.
4. Grab ~10 lines of source around the vulnerable logic, annotating references using `SRC_FILE` + `SRC_FUNCTION` only (no raw line numbers, GitHub URLs, or absolute paths).
5. Replace all placeholders; verify none remain.
6. Save Markdown to output path.
```

# 🧪 Self-Check
- Re-open the written file → scan for `{{` or `}}`; abort if any remain.
- Confirm the heading sequence matches the template exactly.
- Ensure the PoC section explicitly lists the test file path(s) and exact command(s) required to reproduce the issue.
- Search the rendered Markdown for forbidden internal identifiers (`AP`, `SR`, `NORMATIVE_ID`, `@audit`, `@audit-ok`) and replace any occurrences with public-friendly phrasing before finalizing.

# ⛔ Constraints
- **Do not** wrap Markdown in JSON.
- No public URLs for PoC code; assume local testnet execution.
- Never mention internal identifiers like `03_AUDITMAP`, `AP`, `SR`, or any `security-agent/` paths in the generated report.
- All links must be fully-qualified `https://`.
- Redact or translate away any occurrences of `AP`, `SR`, `NORMATIVE_ID`, `@audit`, or `@audit-ok` so they never reach the delivered document.

# ✅ Success Criteria
- Entry with `id == $VULN_ID` found.
- `report_{{TITLE_SLUG}}.md` created and passes placeholder audit.
- PoCs compile via the project’s test runner, e.g.
  ```bash
  # Unit test
  <runner_for_project> <args_to_run> {{UT_PATH}}
  # Integration test (if present)
  <runner_for_project> <args_to_run> {{IT_PATH}}
  ```
- Severity matches the `$SEVERITY` argument when provided; otherwise it is derived using `security-agent/outputs/01_BOUNTY_GUIDELINE.md` with clear internal justification.
