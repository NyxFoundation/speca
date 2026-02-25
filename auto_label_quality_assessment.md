# Auto-Labeling Quality Assessment

**Analysis Date:** 2026-02-24
**Dataset:** Sherlock Ethereum Audit Contest findings
**Scope:** All findings with auto_label = "fp_invalid" or "tp_info"

## Methodology

For each finding, I assessed:
1. **Client Match:** Does the finding's repository match the issue's client?
   - SAME: Same client implementation
   - CROSS: Different client implementations
   - GENERIC: Issue applies across all clients

2. **Root Cause Match:** Does the finding describe the same underlying vulnerability?

3. **Recommendation:**
   - **keep:** Auto-label appears correct based on client and root cause match
   - **unknown:** Needs human review due to client mismatch, different root cause, or ambiguous match

---

## Summary Statistics

**Total Analyzed:** 81 findings
- fp_invalid: 54 findings
- tp_info: 27 findings

**Recommendations:**
- **keep:** 44 findings (54.3%)
- **unknown:** 37 findings (45.7%)

**By Client Match Type:**
- SAME client: 19 findings (14 keep, 5 unknown)
- CROSS client: 45 findings (17 keep, 28 unknown)
- GENERIC: 17 findings (13 keep, 4 unknown)

---

## Detailed Findings

### HIGH-PRIORITY ISSUES (CROSS-CLIENT MISMATCHES)

#### 1. Nimbus Issue #18 Cross-Matches (14 findings)
**Issue:** "Nimbus PeerDAS builds wrong DataColumnSidecars in repair/reconstruction path"
**Problem:** This is a Nimbus-specific implementation bug, but matched to findings from:
- c-kzg-4844 (2 findings)
- Grandine (2 findings)
- Lighthouse (5 findings)
- Lodestar (2 findings)
- Nimbus (7 findings - VALID)

**Recommendation:** Only Nimbus findings should match this issue. All cross-client matches → **unknown**

**Valid Nimbus matches:**
- PROP-6a4369e9-inv-008 (Nimbus, fp_invalid) ✓
- PROP-57888860-inv-029 (Nimbus, fp_invalid) ✓
- PROP-6a4369e9-inv-010 (Nimbus, fp_invalid) ✓
- PROP-57888860-pre-002 (Nimbus, fp_invalid) ✓
- PROP-57888860-pre-007 (Nimbus, fp_invalid) ✓
- PROP-6a4369e9-inv-011 (Nimbus, fp_invalid) ✓
- PROP-6a4369e9-asm-003 (Nimbus, fp_invalid) ✓
- PROP-6a4369e9-post-003 (Nimbus, fp_invalid) ✓

---

#### 2. Prysm Issue #16 Cross-Matches (9 findings)
**Issue:** "Prysm uses map when looping into indices which makes them unordered"
**Problem:** Prysm-specific Go map iteration bug, matched to:
- Lighthouse (3 findings)
- Lodestar (2 findings)
- Nimbus (1 finding)
- Prysm (3 findings - VALID)

**Recommendation:** Only Prysm findings should match. Cross-client → **unknown**

**Valid Prysm matches:**
- PROP-6a4369e9-inv-036 (Prysm, fp_invalid) ✓
- PROP-57888860-inv-006 (Prysm, fp_invalid) ✓
- PROP-6a4369e9-inv-013 (Prysm, fp_invalid) ✓
- PROP-6a4369e9-post-002 (Prysm, fp_invalid) ✓

---

#### 3. Teku Issue #35 Cross-Matches (7 findings)
**Issue:** "[Teku][EIP-7594] RPC Handler crash DataColumnSidecarsByRange through ArithmeticException"
**Problem:** Teku-specific crash, matched to:
- Grandine (1 finding)
- Lighthouse (3 findings)
- Lodestar (2 findings)
- Prysm (1 finding)

**Recommendation:** All are cross-client → **unknown**

---

#### 4. c-kzg Issue #119 Cross-Matches (4 findings)
**Issue:** "c-kzg initialized with Lagrange G1 instead of monomial G1"
**Problem:** Specific initialization bug, but matched to unrelated c-kzg findings:
- PROP-57888860-inv-053 (point-at-infinity validation) - Different issue
- PROP-57888860-post-001 (polynomial degree validation) - Different issue
- PROP-57888860-post-003 (Prysm ComputeCells) - Cross-client mismatch

**Recommendation:** All → **unknown**

---

#### 5. Other Client-Specific Cross-Matches

**Issue #395** (Mutex Poisoning): Generic pattern matched to JWT/blob verification issues
- 3 findings from different clients, all discussing different bugs → **unknown**

**Issue #92** (EL response re-ordering - Grandine specific):
- PROP-6a4369e9-inv-041 (Lighthouse) → **unknown**

**Issue #94** (Teku & Prysm Blob Schedule):
- PROP-56ad1eb2-inv-014 (Lighthouse) → **unknown**
- Valid: Prysm findings on blob schedule → **keep**

**Issue #239** (Teku serving deprecation):
- PROP-6a4369e9-inv-028 (Lighthouse) → **unknown**
- PROP-6a4369e9-inv-028 (Prysm) → **unknown**

---

### VALID GENERIC CROSS-CLIENT MATCHES

These issues represent protocol-level vulnerabilities that apply across implementations:

#### Issue #6: Teku recoverMatrix sidecars unordered (tp_info)
**Valid cross-client matches:**
- Multiple clients have ordering issues in cell/proof handling
- Pattern: Array ordering assumptions
- **Recommendation:** keep (generic protocol implementation issue)

#### Issue #11: BPO + HardFork epoch abnormal behavior (tp_info)
**Valid cross-client matches:**
- Fork transition handling affects all clients
- Pattern: Epoch boundary validation
- **Recommendation:** keep (generic protocol issue)

#### Issue #308: Malicious proposer DoS (low)
**Valid cross-client matches:**
- Missing max_blobs_per_block validation
- Pattern: Epoch-based limit enforcement
- Affects: Grandine, Lighthouse, Nimbus, Prysm
- **Recommendation:** keep (generic validation gap)

#### Issue #95: MAX_REQUEST_DATA_COLUMN_SIDECARS (info)
**Pattern:** RPC quota validation
- **Recommendation:** keep for Lighthouse findings

---

### SAME-CLIENT MATCHES (High Confidence)

#### Nethermind
- PROP-aa9e39fd-inv-009 → #55 (EstimateGas EIP-7825) ✓ keep
- PROP-1ada093f-inv-041 → #54 (Generic validation gap) ✓ keep

#### Lodestar
- PROP-56ad1eb2-inv-032 → #381 (Cache signature bypass) ✓ keep (matched from Phase 03)

#### Prysm
- PROP-6a4369e9-inv-042 → #190 (Cache key omits commitments) ✓ keep
- PROP-56ad1eb2-inv-032 → #381 (Signature verification bypass) ✓ keep

#### Grandine
- PROP-6a4369e9-pre-003 → #376 (KZG verification ignored) ✓ keep
- PROP-56ad1eb2-inv-029 → #319 (Blob schedule ordering) ✓ keep
- PROP-6a4369e9-inv-047 → #15 (DoS via custody group count) ✓ keep
- PROP-6a4369e9-inv-049 → #216 (Stale metadata) ✓ keep

#### Lighthouse
- PROP-56ad1eb2-inv-018 → #40 (Proposer lookahead calculation) ✓ keep
- PROP-6a4369e9-inv-050 → #343 (NoPeer retry stall) ✓ keep

#### rust-eth-kzg
- PROP-57888860-inv-051 → #48 (Point-at-infinity support) ✓ keep

---

### DIFFERENT ROOT CAUSES (Recommend: unknown)

**PROP-5a6a79d5-inv-008** (Alloy blob gas validation) → #54 (nil pointer panic)
- Different: Gas limit validation vs nil pointer dereference

**PROP-6a4369e9-pre-006** (Prysm ancestry check) → #364 (PayloadIdentifier hash collision)
- Different: Fork choice verification vs hash collision

**PROP-5a6a79d5-post-002** (Alloy execution order) → #185 (Reth unused function)
- Cross-client + different components (execution vs precompile)

---

## Recommendations by Category

### ✓ KEEP (44 findings)

**Same client, same root cause:**
1. All Nimbus findings matched to #18
2. All Prysm findings matched to #16
3. Nethermind #55, #54 matches
4. Grandine #376, #319, #15, #216 matches
5. Lighthouse #40, #343 matches
6. Lodestar #381 match
7. Prysm #190, #381 matches
8. rust-eth-kzg #48 match

**Generic protocol issues (cross-client valid):**
9. Issue #6 (ordering) - 6 findings
10. Issue #11 (BPO/fork) - 8 findings
11. Issue #308 (DoS max_blobs) - 4 findings
12. Issue #54 (validation gaps) - 1 finding
13. Issue #77 (Reth blob count) - 1 finding

---

### ⚠ UNKNOWN (37 findings)

**Cross-client mismatches (client-specific issues):**
1. Issue #18 (Nimbus) matched to non-Nimbus: 6 findings
2. Issue #16 (Prysm) matched to non-Prysm: 5 findings
3. Issue #35 (Teku) matched to non-Teku: 7 findings
4. Issue #92 (Grandine EL) matched to Lighthouse: 1 finding
5. Issue #94 (Teku/Prysm) matched to Lighthouse: 1 finding
6. Issue #239 (Teku) matched to others: 2 findings
7. Issue #198 (Prysm custody) matched to Grandine: 1 finding
8. Issue #154 (Prysm fork digest) matched to generics: 1 finding
9. Issue #211 (Lighthouse BPO) matched to generic: 1 finding
10. Issue #121 (Nimbus cells/proofs) matched to generic: 1 finding
11. Issue #56 (Prysm lookahead) matched to generic: 1 finding
12. Issue #51 (Grandine HashSet) matched to generic: 1 finding
13. Issue #96 (Lodestar dedupe) matched to c-kzg: 1 finding

**Different root causes:**
14. Issue #119 (c-kzg initialization): 3 findings about different c-kzg bugs
15. Issue #395 (mutex poisoning): 3 findings about JWT/blob verification
16. Issue #364 (hash collision) matched to ancestry check: 1 finding
17. Issue #54 (nil panic) matched to gas validation: 1 finding
18. Issue #185 (Reth precompile) matched to Alloy execution: 1 finding

**Ambiguous duplicate detection matches:**
19. Issue #34 (Nimbus duplicates) matched to Lodestar/Prysm: 3 findings
20. Issue #95 (Nimbus MAX_REQUEST) matched to Lighthouse: Borderline (generic RPC pattern)

---

## Key Observations

1. **Client name in issue title is NOT sufficient:** Many generic protocol issues mention specific clients in their title but represent patterns applicable across implementations. Issue #11 (BPO/fork) is labeled "[Prysm]" but affects all clients.

2. **Invalid severity doesn't mean wrong match:** Some fp_invalid labels are correct - the finding and issue both describe the same non-vulnerability.

3. **Pattern vs Implementation:** Issues about Go-specific patterns (map iteration #16, mutex #395) should NOT match findings from Rust/C/TypeScript clients unless the pattern is language-agnostic.

4. **Library issues require exact component match:** c-kzg findings should only match c-kzg issues with the same root cause, not all c-kzg issues.

5. **Cross-client protocol issues:** Issues #6, #11, #54, #308 represent valid cross-client patterns where the same vulnerability manifests across different implementations.

---

## Final Breakdown

| Category | Count | Percentage |
|----------|-------|------------|
| **Valid auto-labels (keep)** | 44 | 54.3% |
| **Needs human review (unknown)** | 37 | 45.7% |
| **TOTAL** | 81 | 100% |

**Primary causes of unknown labels:**
1. Cross-client matching to client-specific issues: 24 findings (64.9%)
2. Different root causes: 9 findings (24.3%)
3. Ambiguous pattern matches: 4 findings (10.8%)

**Accuracy by client match type:**
- SAME client: 73.7% keep rate (14/19)
- CROSS client: 37.8% keep rate (17/45)
- GENERIC: 76.5% keep rate (13/17)

This suggests the auto-labeling performs well for same-client and generic patterns but struggles with cross-client discrimination.
