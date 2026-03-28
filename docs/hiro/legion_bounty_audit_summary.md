# Legion Protocol Bug Bounty Audit Summary

**Date**: 2026-03-28/29
**Bounty**: Code4rena Legion Protocol ($10K-$75K)
**Auditor**: SPECA + Claude MAX 20x human wave tactics

## Scope

**In-scope**: 18 contracts (5 factories, 4 sales, 1 capital raise, 2 distribution, 2 vesting, 1 access, 1 registry, 1 token distributor factory, 1 vesting factory)

**Out-of-scope** (critical OOS items that killed findings):
1. Centralization risks
2. Fee-on-transfer and rebasing token incompatibility
3. **Project owners not required to provide ask tokens to pre-liquid sales before withdrawing capital** → killed M-03/Low
4. **Signature reuse allowing multiple investments per sale** → killed M-02
5. Refunding allowed prior to official sale end
6. Test/script/mocks/lib/utils/interfaces directories
7. Previous audit findings
8. MEV/frontrunning attacks
9. Input validation issues
10. Testnet-only bugs

## Methodology

### Phase 1: SPECA Pipeline (Automated)
- 6-phase pipeline (01a→01b→01e→02c→03→04)
- Generated 100 properties, 62 raw findings from 6 parallel audit agents

### Phase 2: Manual Audit (Direct Code Reading)
- Read ALL 18 in-scope contracts line-by-line
- 6 parallel deep audit agents: vesting, distribution, factory+registry, capital raise, sealed bid auction, cross-contract
- CSV pattern matching against 5,354 similar contest issues (C4/Sherlock/CodeHawks)
- Cross-referenced with 5 existing audit PDFs

### Phase 3: Self-Review Checklist
- Applied 10-point severity checklist from `docs/hiro/severity_criteria_and_review_lessons.md`
- §2.1: Permissionless trigger required for Medium+
- §2.6: Trust-role dependency disqualifies

## Findings

### M-01: Transfer Signature Replay (MARGINAL — scope debate)

**Status**: Only surviving candidate, but scope is debatable

- `LegionPositionManager._verifyTransferSignature()` does not include nonce/deadline
- Signature: `(from, to, positionId, msg.sender, address(this), block.chainid)` — no replay protection
- **OOS #4 says "investments" not "transfers"** — this is a TRANSFER signature, different vulnerability
- **BUT**: `LegionPositionManager` is NOT in in_scope_assets list
- **HOWEVER**: The vulnerable function manifests via `transferInvestorPositionWithAuthorization` in all 5 in-scope sale/raise contracts
- Practical exploitability requires position to be transferred back to original owner (narrow window)

**Files**: `outputs/c4_report_HIGH_signature_replay.md` (GitHub Issue: NyxFoundation/security-agent#176)

### M-02: Invest Signature Missing Amount/Nonce/Deadline — **OUT OF SCOPE**

- `_verifyInvestSignature()` hash: `(msg.sender, address(this), block.chainid)` only
- Killed by OOS #4: "Signature reuse allowing multiple investments per sale"

**Files**: `outputs/c4_report_MEDIUM_invest_signature_no_amount.md` (GitHub Issue: NyxFoundation/security-agent#177)

### LOW/QA: withdrawRaisedCapital Missing Guard — **OUT OF SCOPE**

- PreLiquid contracts drop `whenTokensSupplied` modifier
- Killed by OOS #3: "Project owners not required to provide ask tokens"

**Files**: `outputs/c4_report_MEDIUM_withdrawRaisedCapital_missing_guard.md` (GitHub Issue: NyxFoundation/security-agent#178)

### LOW/QA: Missing whenTokensSupplied on claimTokenAllocation

- Defense-in-depth inconsistency, ERC20 transfer acts as natural guard
- Very low practical impact

**Files**: `outputs/c4_report_LOW_missing_whenTokensSupplied.md`

## Attack Surfaces Exhaustively Checked (No Findings)

### Reentrancy
- **No `nonReentrant` modifier** in entire codebase
- All contracts follow CEI pattern correctly
- ERC777 reentrancy scenarios analyzed:
  - `cancel()` reentrancy → blocked by atomic transaction semantics
  - `claimTokenAllocation()` reentrancy → early vesting release possible but no extra tokens
  - `invest()` + `refund()` cross-function → blocked by modifier guards
- **Verdict**: CEI + modifier guards are sufficient; ERC777 risk is low-probability and bidToken is typically USDC/USDT

### Fee Calculations
- `legionFeeOnCapitalRaisedBps * totalCapitalRaised / 10000` — standard basis points
- `legionFeeOnTokensSoldBps * amount / 10000` — same
- Precision: 18-decimal TOKEN_ALLOCATION_RATE_DENOMINATOR used for allocation rates
- `supplyTokens` validates exact fee amounts match expectations
- **Verdict**: No precision loss vulnerability found

### Merkle Proof Verification
- Double-hashing pattern: `keccak256(bytes.concat(keccak256(abi.encode(...))))` — standard OpenZeppelin pattern
- `claimTokensMerkleRoot` and `acceptedCapitalMerkleRoot` set by `onlyLegion`
- `hasSettled` and `hasClaimedExcess` flags prevent double claims
- **Verdict**: Correct implementation

### Factory / EIP-1167 Clone Initialization
- All factories clone + initialize atomically in same transaction
- `_disableInitializers()` in all implementation constructors
- Factory `createX()` functions are `onlyOwner` (except LegionVestingFactory which is permissionless but harmless)
- **Verdict**: No front-running possible

### Vesting Contracts
- `LegionLinearVesting`: Standard VestingWalletUpgradeable + cliff. Correct.
- `LegionLinearEpochVesting`: Epoch-based `_vestingSchedule` override. Math verified for all epoch boundaries.
- `emergencyTransferOwnership` protected by `onlyVestingController`
- **Verdict**: No calculation errors found

### State Machine / Access Control
- Sale lifecycle: invest → refund period → publish results → supply tokens → claim
- Transfer window: after refund, before sale results published
- Cancel: returns `totalCapitalWithdrawn` from project, sets `isCanceled = true`
- All critical functions properly gated by modifiers
- **Verdict**: No state machine violations found

### Position Transfer / Merge
- `_burnOrTransferInvestorPosition`: correctly handles merge (add invested capital) vs transfer
- PreLiquidApprovedSale: also adds `cachedTokenAllocationRate` and `cachedInvestAmount` on merge — mathematically correct
- ERC721 ownership check in `_transfer` prevents unauthorized transfers
- **Verdict**: Correct implementation

### LegionCapitalRaise
- Independent implementation from sale contracts
- Same patterns (signature-based invest, cancel with capital return, position management)
- **Verdict**: No unique vulnerabilities

## Code Quality Assessment

The codebase is **well-written and well-audited** (5 prior audits). The OOS list is comprehensive and covers most of the real attack vectors. The CEI pattern is consistently followed. The main structural weakness (no nonReentrant) is mitigated by correct state management.

## Recommendation

**Submit M-01 (transfer signature replay) only**, with clear argumentation that:
1. OOS #4 specifies "investments" not "transfers"
2. The vulnerability manifests in in-scope contracts via inheritance
3. The impact is position theft/griefing (permissionlessly triggerable with on-chain signature)

Expected outcome: **Low probability of acceptance** due to:
- Narrow exploitation window (requires A→B→A transfer sequence)
- Scope debate (LegionPositionManager not in in_scope_assets)
- May have been found in prior audits (OOS #7)

## Phase 4: Deep Audit Agent Verification (Post-Context-Resume)

6 parallel deep audit agents completed and produced 8 Medium+ findings that initially survived OOS filtering. All 8 were manually verified against actual code and **all eliminated**:

| Finding | Source Agent | Verdict | Reason |
|---------|------------|---------|--------|
| abi.encodePacked collision in _verifyValidPosition | merkle | FP | All types fixed-size (address, uint256, enum) — no collision possible |
| cancelLocked permanent fund lock | sealed_bid | OOS #1 | Centralization risk — requires onlyLegion admin to malfunction |
| Position merge rate overclaim | fees | FP | Rate = absolute share of supply, sum is correct; claim overwrites with server-signed value |
| Merkle proof replay via merge | merkle | FP | Transfer requires hasClaimedExcess=true; excess Merkle leaf is address-bound |
| CapitalRaise cancel() missing whenTokensNotSupplied | access_control | FP | CapitalRaise has no token supply concept — modifier N/A |
| Transfer sig no expiry | sig_patterns | Duplicate | Already M-01 |
| Vesting sig no expiry (stale terms) | sig_patterns | FP | hasSettled single-use guard prevents exploitation |
| abi.encodePacked collision in CapitalRaise | merkle | FP | Same as above — all fixed-size types |

**Total from deep audit agents: 0 new confirmed findings.**

## Final Recommendation

**Submit M-01 (transfer signature replay) only.** This is the sole surviving candidate after:
- SPECA automated pipeline (62 raw → 3 candidates)
- Manual line-by-line audit of all 18 contracts
- 6 parallel deep audit agents (8 candidates → 0 confirmed)
- Self-review checklist application
- OOS filtering

## Files Modified/Created

- `outputs/c4_report_HIGH_signature_replay.md` — M-01 report
- `outputs/c4_report_MEDIUM_invest_signature_no_amount.md` — M-02 report (OOS)
- `outputs/c4_report_MEDIUM_withdrawRaisedCapital_missing_guard.md` — downgraded to Low (OOS)
- `outputs/c4_report_LOW_missing_whenTokensSupplied.md` — QA report
- `outputs/manual_audit_*.json` — 6 parallel audit agent raw results
- `outputs/legion_similar_issues.csv` — 5,354 filtered similar contest issues
- `scripts/filter_similar_for_legion.py` — CSV filter script

## Git State

- Branch: `hiro/c4-legion-bounty`
- Remote: `origin` (NyxFoundation/security-agent)
- GitHub Issues: #176, #177, #178
