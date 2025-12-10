


---
Description: Fuzzing Test Generator & Self-Verifying Checklist Validator
Usage: `/03b_fuzzing CHECKLIST_ID=... [OUTPUT_PATH=...]`
Example: `/03b_fuzzing CHECKLIST_ID="CL-ZK-POSEIDON-PARAM-PINNING" OUTPUT_PATH="contracts/test/fuzz/FuzzPoseidonParamPinning.t.sol"`
Example (auto-path): `/03b_fuzzing CHECKLIST_ID="CL-ZK-POSEIDON-PARAM-PINNING"`
Arguments:
- **$CHECKLIST_ID**: value of `items[].id` in `security-agent/outputs/02_CHECKLIST.json`.
- **$OUTPUT_PATH** (optional): destination path for the generated fuzzing test file. If omitted, the path will be auto-generated based on the checklist item's language, domain, and existing test directory structure.
---

Create & validate a comprehensive fuzzing test that verifies **$CHECKLIST_ID** through property-based testing and invariant checking.

**Always use /serena for these development tasks to maximize token efficiency.**
**Never assume the implementation language; detect and reuse the project's existing language, test harness, fixtures, and mocks.**

# 📥 Auto-load from 02_CHECKLIST.json

1. **Read** `security-agent/outputs/02_CHECKLIST.json`.
2. **Locate** the entry where `items[].id == $CHECKLIST_ID`.
3. **Extract**
   - `CHECK_TITLE` ← `items[].title`
   - `CHECK_PROPERTY_ID` ← `items[].property_id`
   - `CHECK_BUG_CLASS` ← `items[].bug_class`
   - `CHECK_RISK_CATEGORY` ← `items[].risk_category`
   - `CHECK_SEVERITY` ← `items[].severity_hint`
   - `CHECK_DOMAINS` ← `items[].domains[]`
   - `CHECK_LANGUAGES` ← `items[].languages[]`
   - `CHECK_FILE_GLOBS` ← `items[].file_globs[]`
   - `CHECK_DETECTION_PROCEDURE` ← `items[].detection_procedure`
   - `CHECK_EXECUTABLE_CHECKS` ← `items[].executable_checks`
   - `CHECK_EVIDENCE_PROBES` ← `items[].evidence_probes`
   - `CHECK_OK_IF` ← `items[].ok_if`
   - `CHECK_NOT_OK_IF` ← `items[].not_ok_if`
   - `CHECK_PATTERNS` ← `items[].patterns`
   - `CHECK_BAD_PATH_LIBRARY` ← `items[].bad_path_library`
   - `CHECK_PARITY_VECTORS` ← `items[].parity_vectors`
   - `TITLE_SLUG` ← `CHECK_TITLE` transformed to PascalCase using ASCII letters/digits only. Replace punctuation/spaces with empty string, capitalize first letter of each word, and ensure length ≤ 50 characters.
4. **If not found** → abort with error `"Checklist item '$CHECKLIST_ID' not found in 02_CHECKLIST.json"`.

# 🗂️ Auto-generate OUTPUT_PATH (if not provided)

If `$OUTPUT_PATH` is not provided, generate it automatically based on the checklist item:

1. **Detect primary language** from `CHECK_LANGUAGES[]`:
   - If contains `"solidity"` → use Solidity
   - Else if contains `"rust"` → use Rust
   - Else if contains `"typescript"` or `"javascript"` → use TypeScript
   - Else → use the first language in the array

2. **Locate existing test directory**:
   - **Solidity**: Look for `contracts/test/`, `test/`, `src/test/`
   - **Rust**: Look for `tests/`, `zkp/tests/`, `src/tests/`
   - **TypeScript**: Look for `test/`, `tests/`, `__tests__/`
   - If multiple directories exist, prefer the one with the most existing test files

3. **Determine subdirectory**:
   - Create or use a `fuzz/` subdirectory within the test directory
   - If `fuzz/` doesn't exist, create it

4. **Generate filename**:
   - **Solidity**: `Fuzz{TITLE_SLUG}.t.sol`
   - **Rust**: `fuzz_{title_slug_snake_case}.rs`
   - **TypeScript**: `fuzz.{title_slug_kebab_case}.test.ts`
   - Ensure filename length ≤ 60 characters (truncate `TITLE_SLUG` if necessary)

5. **Construct full path**:
   - Combine: `{test_directory}/fuzz/{filename}`
   - Example (Solidity): `contracts/test/fuzz/FuzzPoseidonParamPinning.t.sol`
   - Example (Rust): `zkp/tests/fuzz/fuzz_poseidon_param_pinning.rs`
   - Example (TypeScript): `test/fuzz/fuzz.poseidon-param-pinning.test.ts`

6. **Verify path doesn't conflict**:
   - If file already exists, append a numeric suffix: `_2`, `_3`, etc.
   - Example: `FuzzPoseidonParamPinning_2.t.sol`

7. **Set `$OUTPUT_PATH`** to the generated path and proceed with test generation.

# 🎯 Goals

1. Generate the fuzzing test in the **project's native stack** (language, test runner, fuzzing framework).
2. The test must **comprehensively verify the checklist item** through:
   - **Property-based testing**: Test the property across a wide input space
   - **Invariant checking**: Verify invariants hold under all conditions
   - **Boundary testing**: Test edge cases and boundary conditions
   - **Negative testing**: Verify that violations are properly detected and rejected
3. Reuse nearby tests, fixtures, and mocks instead of re-implementing them.
4. Keep the artifact focused, ≤ 200 LOC per test function, and free from external binaries or network dependencies unless already standard in the project.
5. **Never modify the checklist item's intent**; faithfully test what the checklist specifies.

# 🧭 Language-specific Guidelines

## Solidity (Foundry)

- **Framework**: Use Foundry's built-in fuzzing (`testFuzz*`) and invariant testing (`invariant*`)
- **Test file naming**: `Fuzz{TITLE_SLUG}.t.sol`
- **Test function naming**: `testFuzz_{property_name}(uint256 x, address y, ...)` for property-based tests
- **Invariant function naming**: `invariant_{invariant_name}()` for invariant tests
- **Assumptions**: Use `vm.assume()` to constrain fuzzing inputs to valid ranges
- **Assertions**: Use `assertEq`, `assertLt`, `assertGt`, `assertGe`, `assertLe` for precise checks
- **Mocking**: Use `vm.mockCall`, `vm.expectRevert`, `vm.expectEmit` for controlled scenarios
- **Runs**: Configure `runs` in `foundry.toml` or use `forge test --fuzz-runs 10000`
- **Invariant targets**: Define target contracts in `setUp()` and use `targetContract(address)`

## Rust (cargo test + proptest/quickcheck)

- **Framework**: Use `proptest` or `quickcheck` for property-based testing
- **Test file naming**: `fuzz_{title_slug}.rs` in `tests/` directory
- **Test function naming**: `#[test] fn fuzz_{property_name}()` or `proptest! { #[test] fn prop_{property_name}(...) }`
- **Property macros**: Use `proptest!` macro for property-based tests
- **Strategies**: Define custom strategies for complex types using `prop_compose!`
- **Assertions**: Use `assert!`, `assert_eq!`, `prop_assert!`, `prop_assert_eq!`
- **Runs**: Configure `cases` in `ProptestConfig` (default 256, increase for thorough testing)

## TypeScript/JavaScript (fast-check)

- **Framework**: Use `fast-check` for property-based testing
- **Test file naming**: `fuzz.{title_slug}.test.ts`
- **Test function naming**: `test('fuzz: {property_name}', () => { fc.assert(...) })`
- **Arbitraries**: Use `fc.integer()`, `fc.string()`, `fc.array()`, etc. for input generation
- **Assertions**: Use `expect()` from Jest/Vitest or `assert()` from Node
- **Runs**: Configure `numRuns` in `fc.assert()` options (default 100, increase for thorough testing)

# 📝 Fuzzing Test Design

## Phase 1: Understand the Checklist Item

1. **Read the detection procedure**: Understand the step-by-step verification process
2. **Identify the property**: Extract the core property being tested from `CHECK_OK_IF` and `CHECK_NOT_OK_IF`
3. **Locate target files**: Use `CHECK_FILE_GLOBS` to find the implementation files
4. **Extract patterns**: Use `CHECK_PATTERNS` to identify code patterns to test
5. **Review bad paths**: Use `CHECK_BAD_PATH_LIBRARY` to understand negative scenarios

## Phase 2: Design Test Cases

### A. Property-Based Tests

For each property in `CHECK_OK_IF`:
1. **Define input space**: Determine the valid input range for fuzzing
2. **Generate inputs**: Use the fuzzing framework to generate diverse inputs
3. **Apply constraints**: Use assumptions to filter invalid inputs
4. **Execute property**: Run the code under test with fuzzed inputs
5. **Assert property holds**: Verify the property is satisfied

### B. Invariant Tests

For each invariant implied by the checklist:
1. **Define invariant**: Extract the invariant from `CHECK_OK_IF` and `CHECK_DETECTION_PROCEDURE`
2. **Define state transitions**: Identify all operations that modify state
3. **Execute transitions**: Fuzz all possible state transitions
4. **Check invariant**: Verify the invariant holds after each transition

### C. Boundary Tests

For each boundary condition:
1. **Identify boundaries**: Extract from `CHECK_PATTERNS` and `CHECK_NOT_OK_IF`
2. **Test at boundaries**: Test at min, max, zero, overflow, underflow
3. **Test near boundaries**: Test at boundary ± 1
4. **Assert behavior**: Verify correct behavior at boundaries

### D. Negative Tests

For each violation scenario in `CHECK_NOT_OK_IF` and `CHECK_BAD_PATH_LIBRARY`:
1. **Craft violation**: Create inputs that should violate the property
2. **Execute code**: Run the code with violating inputs
3. **Assert rejection**: Verify the violation is detected and rejected (revert, error, false return)

## Phase 3: Implement Mocks and Fixtures

1. **Scan existing tests**: Look for similar tests in the same directory
2. **Reuse fixtures**: Import and reuse existing setup functions, mock contracts, test data
3. **Create minimal mocks**: Only create new mocks if necessary for isolation
4. **Cross-component mocking**: For tests spanning multiple components (e.g., contracts + ZK circuits):
   - Mock the unavailable component (e.g., mock ZK proof verification in contract tests)
   - Focus on the component within the test scope
   - Document the mocking assumptions in comments

# 🛠️ Build & Run

## Auto-detect Test Environment

1. **Inspect project structure**:
   - Solidity: Look for `foundry.toml`, `forge` in PATH
   - Rust: Look for `Cargo.toml`, check `[dev-dependencies]` for `proptest` or `quickcheck`
   - TypeScript: Look for `package.json`, check `devDependencies` for `fast-check`

2. **Derive test command**:
   - Solidity/Foundry: `forge test --match-path $OUTPUT_PATH --fuzz-runs 10000 -vv`
   - Rust/proptest: `cargo test --test fuzz_{title_slug} -- --nocapture`
   - TypeScript/fast-check: `npm test -- --testPathPattern=$OUTPUT_PATH`

3. **Check for custom scripts**: Inspect `Makefile`, `package.json` scripts, `justfile` for custom test commands

## Execution Strategy

```
FOR attempt in 1..=3:
    generate fuzzing test based on checklist item
    compile/build the test
    if build fails:
        analyze error and fix imports/types/syntax
        continue to next attempt
    run the fuzzing test
    if test passes:
        record PASS ✅
        break
    else if test fails due to property violation:
        analyze failure and verify it's a legitimate issue
        if legitimate issue found:
            record FAIL with evidence 🔴
            break
        else:
            adjust test logic without changing checklist intent
            continue to next attempt
    else if test fails due to test code bug:
        fix test code bug
        continue to next attempt

if attempt > 3:
    record GAVE_UP with error details 🆘
```

# 📤 Output Artifacts

1. **Fuzzing test file** → `{{OUTPUT_PATH}}`
   - Filename must include `fuzz` or `Fuzz` and the `TITLE_SLUG`
   - Keep the filename component ≤ 60 characters

2. **Test metadata** → append to `security-agent/outputs/03b_FUZZING_RESULTS.json`:
   ```jsonc
   {
     "checklist_id": "{{CHECKLIST_ID}}",
     "property_id": "{{CHECK_PROPERTY_ID}}",
     "title": "{{CHECK_TITLE}}",
     "test_file": "{{OUTPUT_PATH}}",
     "language": "solidity|rust|typescript",
     "framework": "foundry|proptest|fast-check",
     "test_type": "property-based|invariant|boundary|negative",
     "build_status": "success|failed",
     "test_status": "pass|fail|gave_up",
     "test_runs": 10000,
     "failures_found": 0,
     "failure_examples": [],
     "compile_attempts": 1,
     "test_attempts": 1,
     "execution_time_ms": 1234,
     "coverage": {
       "ok_if_conditions": ["condition1", "condition2"],
       "not_ok_if_conditions": ["violation1", "violation2"],
       "patterns_tested": ["pattern1", "pattern2"],
       "bad_paths_tested": ["bad_path1", "bad_path2"]
     },
     "notes": "Additional observations or limitations",
     "created_at": "<ISO-8601 timestamp>"
   }
   ```

3. **Run command** → provide the full command that executes just this fuzzing test

# 🔍 Test Generation Algorithm

## Step 1: Load Checklist Item
```
item = load_checklist_item($CHECKLIST_ID)
if not item:
    abort("Checklist item not found")
```

## Step 2: Analyze Checklist Item
```
properties = extract_properties(item.ok_if, item.not_ok_if)
invariants = extract_invariants(item.detection_procedure)
boundaries = extract_boundaries(item.patterns)
violations = extract_violations(item.bad_path_library, item.not_ok_if)
```

## Step 3: Detect Test Environment
```
language = detect_language(item.languages, item.file_globs)
framework = detect_fuzzing_framework(language)
test_template = load_template(language, framework)
```

## Step 4: Generate Test Code
```
test_code = test_template.render(
    title_slug=TITLE_SLUG,
    properties=properties,
    invariants=invariants,
    boundaries=boundaries,
    violations=violations,
    file_globs=item.file_globs,
    patterns=item.patterns
)
write_file(OUTPUT_PATH, test_code)
```

## Step 5: Compile and Run
```
FOR attempt in 1..=3:
    compile_result = compile(OUTPUT_PATH)
    if compile_result.failed:
        fix_compile_errors(OUTPUT_PATH, compile_result.errors)
        continue
    
    test_result = run_fuzzing_test(OUTPUT_PATH)
    if test_result.passed:
        record_success(test_result)
        break
    else if test_result.failed_due_to_property_violation:
        record_failure(test_result)
        break
    else:
        fix_test_logic(OUTPUT_PATH, test_result.errors)
        continue

if attempt > 3:
    record_gave_up()
```

# 🛡️ Test Quality Requirements

## Faithfulness to Checklist

- **Never change the intent**: The test must verify exactly what the checklist item specifies
- **Cover all conditions**: Test all `ok_if` and `not_ok_if` conditions
- **Test all patterns**: Include tests for all patterns in `CHECK_PATTERNS`
- **Test all bad paths**: Include tests for all scenarios in `CHECK_BAD_PATH_LIBRARY`

## Comprehensiveness

- **Input space coverage**: Fuzz across the entire valid input space
- **Edge cases**: Test boundaries, zero, max, overflow, underflow
- **State space coverage**: For invariant tests, cover all possible state transitions
- **Negative cases**: Test that violations are properly rejected

## Correctness

- **Precise assertions**: Use exact equality checks where appropriate
- **Meaningful failures**: Failure messages should clearly indicate what property was violated
- **No false positives**: Constrain inputs to avoid testing invalid scenarios
- **No false negatives**: Ensure violations are actually detected

## Performance

- **Reasonable runtime**: Fuzzing tests should complete within 60 seconds for 10000 runs
- **Efficient mocking**: Mock only what's necessary for isolation
- **Minimal setup**: Keep `setUp()` or fixture setup minimal and fast

# 🤖 Self-Repair Loop

## Compile Error Handling (max 3 attempts)

1. **Analyze error**: Parse compiler/build error messages
2. **Categorize error**:
   - Import errors → Fix import paths, add missing dependencies
   - Type errors → Adjust types to match actual implementation
   - Syntax errors → Fix syntax mistakes
   - Missing symbols → Import or define missing symbols
3. **Apply fix**: Modify test code to fix the error
4. **Retry**: Attempt compilation again
5. **Give up**: After 3 failed attempts, record error and abort

## Test Failure Handling (max 3 attempts)

1. **Analyze failure**: Parse test failure messages and logs
2. **Categorize failure**:
   - Property violation → Legitimate issue found, record and report
   - Test logic bug → Fix test code without changing checklist intent
   - Environmental issue → Adjust mocks or fixtures
3. **Apply fix**: Modify test code if it's a test logic bug
4. **Retry**: Run test again
5. **Give up**: After 3 failed attempts, record failure and abort

## Giving Up Gracefully

When giving up after 3 attempts:
1. **Record detailed error**: Include full error messages and stack traces
2. **Document attempts**: List all attempted fixes
3. **Suggest manual intervention**: Provide hints for manual debugging
4. **Update metadata**: Set `test_status: "gave_up"` in output JSON

# ⛔ Constraints

## Do Not Modify

- **Production code**: Never modify implementation files
- **Checklist intent**: Never change what the checklist item is testing
- **Dependencies**: Do not add new dependencies beyond those already in the project

## Do Modify

- **Test code**: Freely modify the generated test to fix bugs
- **Imports**: Adjust imports to match actual project structure
- **Mocks**: Create or adjust mocks as needed for isolation

## Mocking Strategy for Cross-Component Tests

When a checklist item spans multiple components (e.g., `domains: ["smart-contract", "zk"]`):

1. **Determine primary component**: Use `CHECK_FILE_GLOBS` to identify the primary component
2. **Mock secondary components**: Create minimal mocks for components outside the test scope
3. **Document assumptions**: Add comments explaining what's mocked and why
4. **Example**:
   ```solidity
   // Mock: Assumes ZK proof verification always succeeds
   // In production, this would call the actual Groth16 verifier
   function mockProofVerification(bytes memory proof) internal pure returns (bool) {
       return proof.length > 0; // Simplified mock
   }
   ```

# ✅ Success Criteria

- Checklist item with `id == $CHECKLIST_ID` located and processed
- Fuzzing test generated in the project's native language and framework
- Test compiles successfully (or gave up after 3 attempts with clear error)
- Test runs successfully (or gave up after 3 attempts with clear error)
- Test faithfully verifies all conditions in the checklist item
- Test covers all `ok_if`, `not_ok_if`, `patterns`, and `bad_path_library` scenarios
- Metadata appended to `03b_FUZZING_RESULTS.json` with accurate status
- Run command provided for manual execution

# 📊 Coverage Tracking

Track which parts of the checklist item were tested:

```jsonc
"coverage": {
  "ok_if_conditions": [
    "condition1: tested ✅",
    "condition2: tested ✅",
    "condition3: not tested (reason) ⚠️"
  ],
  "not_ok_if_conditions": [
    "violation1: tested ✅",
    "violation2: tested ✅"
  ],
  "patterns_tested": [
    "pattern1: tested ✅",
    "pattern2: not applicable ⚠️"
  ],
  "bad_paths_tested": [
    "bad_path1: tested ✅",
    "bad_path2: could not mock (reason) ⚠️"
  ]
}
```

# 🎓 Examples

## Example 1: Solidity Property-Based Test

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {zERC20} from "../../src/zERC20.sol";

/// @title FuzzBurnMintBalance
/// @notice Fuzzing test for CL-SMART-CONTRACT-BURN-MINT-BALANCE
/// @dev Verifies that total supply equals sum of balances minus burned tokens
contract FuzzBurnMintBalance is Test {
    zERC20 internal token;
    
    function setUp() public {
        token = new zERC20();
        token.initialize("Test", "TST", address(this));
        token.setMinter(address(this));
    }
    
    /// @notice Property: totalSupply == sum(balances) - burned
    function testFuzz_totalSupplyInvariant(
        address[] memory recipients,
        uint248[] memory amounts
    ) public {
        // Constrain inputs
        vm.assume(recipients.length > 0 && recipients.length <= 10);
        vm.assume(recipients.length == amounts.length);
        
        uint256 expectedSupply = 0;
        
        // Mint tokens to recipients
        for (uint i = 0; i < recipients.length; i++) {
            vm.assume(recipients[i] != address(0));
            vm.assume(amounts[i] > 0);
            
            token.mint(recipients[i], amounts[i]);
            expectedSupply += amounts[i];
        }
        
        // Verify invariant
        assertEq(token.totalSupply(), expectedSupply, "total supply mismatch");
    }
}
```

## Example 2: Rust Property-Based Test

```rust
use proptest::prelude::*;
use zkp::utils::poseidon::circom_poseidon_hash;

proptest! {
    /// Property: Poseidon hash is deterministic
    #[test]
    fn fuzz_poseidon_determinism(
        input1 in any::<[u8; 32]>(),
        input2 in any::<[u8; 32]>()
    ) {
        let hash1_a = circom_poseidon_hash(&[input1.into(), input2.into()]);
        let hash1_b = circom_poseidon_hash(&[input1.into(), input2.into()]);
        
        // Same inputs should produce same hash
        prop_assert_eq!(hash1_a, hash1_b);
        
        // Different inputs should produce different hash (with high probability)
        if input1 != input2 {
            let hash2 = circom_poseidon_hash(&[input2.into(), input1.into()]);
            prop_assert_ne!(hash1_a, hash2);
        }
    }
}
```

---

**Remember**: The goal is to create comprehensive, faithful, self-verifying fuzzing tests that prove the checklist item is satisfied (or find violations). Never compromise the checklist's intent for the sake of making tests pass.
