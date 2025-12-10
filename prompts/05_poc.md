


---
Description: PoC Generator & Self-Verifying Tests
Usage: `/05_poc TYPE=... VULN_ID=... OUTPUT_PATH=...`
Example: `/05_poc TYPE="unit" VULN_ID="03523523" OUTPUT_PATH="crates/net/network/src/transactions/poc_reentrancy.rs"`
Arguments:
- **$TYPE**: `unit`, `it`, or `e2e`. Selects the granularity of the PoC.
- **$VULN_ID**: value of `audit_items[].id` in `03_AUDITMAP.json`.
- **$OUTPUT_PATH**: destination path for the generated test or scenario file.
---

Create & validate a minimal PoC that reproduces **$VULN_ID** at the chosen scope.

**Always use /serena for these development tasks to maximize token efficiency.**
**Never assume the implementation language; detect and reuse the project's existing language, test harness, fixtures, and mocks.**

# 📥 Auto-load from 03_AUDITMAP.json
1. **Read** `security-agent/outputs/03_AUDITMAP.json`.
2. **Locate** the entry where `audit_items[].id == $VULN_ID`.
3. **Extract**
   - `VULN_SNIPPET` ← `audit_items[].snippet`
   - `TARGET_FILE` ← `audit_items[].file` + `:L` + `audit_items[].line`
   - `VULN_TITLE_RAW` ← `audit_items[].description`
   - `VULN_TITLE` ← text before the first colon (`:`) in `VULN_TITLE_RAW`, or the full string if no colon exists. If empty, craft a concise fallback title (avoid embedding `$VULN_ID`).
   - `TITLE_SLUG` ← `VULN_TITLE` transformed to lowercase snake_case using ASCII letters/digits/underscores only. Replace punctuation/spaces with `_`, collapse repeats, strip outer `_`, and ensure length ≤ 40 characters (trim filler words or truncate meaningfully if needed).
   - `EXISTING_POC_FILES` ← array of all `poc_tests[].file`, `integration_tests[].file`, and `e2e_tests[].file` in the vulnerability entry (if any).
4. **If not found** → abort with error `"Vulnerability '$VULN_ID' not found in 03_AUDITMAP.json"`.

# 🎯 Goals
1. Generate the PoC in the **project's native stack** (language, test runner, mocks, fixtures).
2. The PoC must **pass only while the vulnerability exists** and **fail once the bug is fixed**.
3. Reuse nearby tests, fixtures, and mocks instead of re-implementing them.
4. Keep the artifact focused, ≤ 120 LOC, and free from external binaries or network dependencies unless already standard in the project.

# 🧭 TYPE-specific Guidelines
- **$TYPE = `unit`**
  - Work within the smallest available test target (module-level, crate-level, package-level, etc.).
  - Prefer in-memory mocks or harnesses already used in unit tests.
  - Output must be a single test file containing at least one `poc_{TITLE_SLUG}` test.
- **$TYPE = `it`** (integration)
  - Place the file alongside existing integration tests (use $OUTPUT_PATH).
  - Attempt to reuse helpers from `EXISTING_POC_FILES` (e.g., a prior unit PoC) and other integration fixtures.
  - Cover the full module/system interaction needed to surface the bug.
- **$TYPE = `e2e`**
  - Target the highest level available (CLI, API, contract deployment, workflow script, etc.).
  - Compose the scenario using production-like flows, leveraging existing end-to-end harnesses or scripts.
  - If the repository lacks e2e scaffolding, fall back to the closest black-box executable or smoke test framework already present.

# 📝 Attack-Scenario Design
1. Locate the code containing `VULN_SNIPPET` and understand the full execution path.
2. Identify required preconditions, fixtures, or deployed components.
3. Design an Arrange–Act–Assert sequence that triggers the bug with minimal setup.
4. Embed assertions proving both the vulnerable outcome and the expected healthy behaviour after a hypothetical fix.

# 🛠️ Build & Run
* Inspect repository metadata (`Cargo.toml`, `package.json`, `pytest.ini`, `go.mod`, etc.) to **auto-detect the correct test runner**.
* Use the project's primary language and frameworks exactly as configured; do not introduce alternative stacks unless already present.
* Derive the execution command dynamically, e.g.:
  - Rust → `cargo test --test poc_{{TITLE_SLUG}} -- --nocapture`
  - Node → `npm test -- --runTestsByPath $OUTPUT_PATH`
  - Python → `pytest $OUTPUT_PATH -k poc_{{TITLE_SLUG}} -vv`
  - Solidity/Foundry → `forge test --match-test poc_{{TITLE_SLUG}} -vv`
* If the project uses custom test scripts, mirror their invocation (check Makefiles, package scripts, etc.).

# 📤 Output Artifacts
1. **PoC file** → `{{OUTPUT_PATH}}`
   - Filename must include `poc_{TITLE_SLUG}` and must not include `$VULN_ID`.
   - Keep the filename component ≤ 50 characters; shorten the slug if necessary.
2. **Run command** → provide the full command that executes just this PoC within the native test runner.
3. **Status JSON** → append to the vulnerability entry:
   - For `unit`:
     ```jsonc
     {
       "poc_tests": [{
         "type": "unit",
         "file": "{{OUTPUT_PATH}}",
         "build_passed": true,
         "test_result": "pass_when_exploitable",
         "attempts": 1,
         "created_at": "<timestamp>"
       }]
     }
     ```
   - For `it`:
     ```jsonc
     {
       "integration_tests": [{
         "type": "integration",
         "file": "{{OUTPUT_PATH}}",
         "build_passed": true,
         "test_passed_when_bug_present": true,
         "attempts": 1,
         "created_at": "<timestamp>"
       }]
     }
     ```
   - For `e2e`:
     ```jsonc
     {
       "e2e_tests": [{
         "type": "e2e",
         "file": "{{OUTPUT_PATH}}",
         "build_passed": true,
         "test_passed_when_bug_present": true,
         "attempts": 1,
         "created_at": "<timestamp>"
       }]
     }
     ```

# 🔍 Generation Algorithm
```
PLAN = global plan()
FOR attempt in 1..=4:
    scaffold PoC using project-native mocks & fixtures
    if build succeeds:
        run targeted test command
        if exploit triggers while bug present: break ✅
    else:
        if attempt == 4: ask user 🆘
        adjust imports/types without diluting exploit
```

# 🛡️ False-Positive Mitigation
* Implement guard assertions verifying both the buggy behaviour and the expected behaviour after a simulated fix (e.g., toggling a flag, patch stub, or in-test check).
* Avoid silent failures (no unchecked `unwrap()`/`expect()` unless idiomatic for the stack).
* Log key metrics (`eprintln!`, `tracing`, `console.log`, etc.) to aid manual review.

# 🤖 Self-Repair Loop (max 3)
* If the build or test run fails for reasons unrelated to the exploit, iterate by adapting imports, feature flags, or harness wiring.
* After 3 unsuccessful corrections, output `Need guidance: <stderr snippet>`.

# ⛔ Constraints
* Do **not** modify production logic or add new dependencies beyond those already declared.
* Maintain compatibility with existing project tooling; prefer extending current mocks/fixtures over inventing new infrastructure.
* Keep PoC files self-contained and ≤ 120 LOC unless the existing style clearly requires more.

# ✅ Success Criteria
* Entry with `id == $VULN_ID` located and processed.
* PoC runs via the detected native runner and fails once the vulnerability is fixed.
* Status JSON appended to the correct entry with accurate metadata.
* Artifact adheres to project language, environment, and naming standards.
