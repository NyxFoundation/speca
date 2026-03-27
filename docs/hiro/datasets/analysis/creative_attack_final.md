# Creative Attack Surface Analysis: Chainlink Payment Abstraction V2

## Final Novel Finding

### M-NEW: `GPV2CompatibleAuction._onAuctionStart` Approval Based on Snapshot Balance Creates CowSwap Order Ceiling That Diverges From Actual Auctionable Balance

**Severity:** Medium
**Affected Contract:** `GPV2CompatibleAuction.sol` (line 92)
**Root Cause:** The vault relayer approval is set once at auction start and never adjusted upward, creating a hard ceiling on CowSwap settlement capacity that permanently diverges from the contract's true auctionable balance when tokens arrive after auction start.

---

#### Description

When `performUpkeep` starts an auction, `_onAuctionStart` approves the CowSwap vault relayer for exactly `balanceOf(address(this))` at that moment:

```solidity
// GPV2CompatibleAuction.sol L86-93
function _onAuctionStart(address asset) internal override {
    super._onAuctionStart(asset);
    IERC20(asset).forceApprove(i_gpV2VaultRelayer, IERC20(asset).balanceOf(address(this)));
}
```

The `isValidSignature` function (L144) validates CowSwap orders against the **current** `balanceOf`:

```solidity
uint256 assetInBalance = order.sellToken.balanceOf(address(this));
if (order.sellAmount > assetInBalance) {
    revert InsufficientAssetInBalance(...);
}
```

This creates a discrepancy: `isValidSignature` may approve an order for an amount that the vault relayer lacks allowance to actually pull. The CowSwap settlement would then revert during the token transfer phase (after validation passed), wasting solver gas and blocking the settlement batch.

#### Attack Scenario

1. Auction for `tokenA` starts via `performUpkeep`. Balance is 1000 tokenA. Vault relayer approval = 1000.
2. A direct `bid()` purchases 600 tokenA. Balance drops to 400. Approval remains 1000 (unused approval portion = 600).
3. An external source sends 800 tokenA directly to the auction contract (e.g., a second `performUpkeep` by a different automation keeper that calls `transferForSwap` for the same asset through a different code path, or direct token transfers from users who mistakenly send to the contract).
4. Balance is now 1200. Approval is still 1000.
5. A CowSwap solver creates a partially-fillable sell order for 1100 tokenA. `isValidSignature` passes (1100 <= 1200 balance, and buyAmount >= minBuyAmount at current price).
6. CowSwap settlement calls `transferFrom(auctionContract, ..., 1100)` via the vault relayer. This fails because approval is only 1000.
7. The entire settlement batch may revert, affecting other orders in the same batch.

The inverse is also possible and more problematic in the context of the existing "Approval desync" note:

1. Auction starts with balance 1000 -> approval 1000.
2. Direct `bid()` takes 900 tokenA -> balance 100, approval still 1000.
3. Solver creates order for 100 tokenA. `isValidSignature` passes.
4. Vault relayer has plenty of approval (1000) but only 100 balance exists. This is fine -- the CowSwap settlement succeeds.
5. Now, imagine a more complex scenario: solver creates a PARTIALLY fillable order for 1000 tokenA (matching the approval). `isValidSignature` rejects because `1000 > 100` (current balance).

While scenario 2 is self-correcting, scenario 1 (approval < balance) is the problematic one. It silently blocks CowSwap settlements for amounts between the approval and the actual balance, with no recovery mechanism short of ending and restarting the auction.

#### Why This Differs From Known "Approval Desync (Low)"

The known finding notes approval desync only "wastes solver gas." This analysis demonstrates a broader impact:

- **CowSwap batch contamination**: A single failed order can revert the entire CowSwap settlement batch, affecting unrelated orders from other protocols settled in the same batch. This is an externality beyond "wasted solver gas."
- **No self-correction**: Unlike balance decreases (where the order simply fails validation in `isValidSignature`), approval-capped scenarios pass validation but fail during execution. There is no on-chain mechanism to increase the approval mid-auction.
- **Compounding effect**: If the `FeeAggregator.transferForSwap` or any other legitimate mechanism sends tokens to the auction contract during an active auction (e.g., the same token is received via CCIP bridging to the FeeAggregator which then gets pulled), the gap between approval and balance widens irreversibly for that auction cycle.

#### Recommended Mitigation

Set approval to `type(uint256).max` in `_onAuctionStart` instead of `balanceOf`:

```solidity
function _onAuctionStart(address asset) internal override {
    super._onAuctionStart(asset);
    IERC20(asset).forceApprove(i_gpV2VaultRelayer, type(uint256).max);
}
```

This is safe because:
1. The vault relayer is an immutable, trusted Chainlink/CowSwap infrastructure contract.
2. `isValidSignature` already bounds the sellable amount by the current balance.
3. The approval is revoked to 0 in `_onAuctionEnd`.
4. `forceApprove` handles tokens that don't allow setting approval from non-zero to non-zero.

Alternatively, re-approve to the current balance at the start of each `isValidSignature` call (but this changes the function from `view` to state-modifying, which is incompatible with EIP-1271).

---

## Exhaustive Analysis of All Investigated Angles

### Angles Verified and Confirmed NOT Exploitable

| # | Angle | Verdict | Reasoning |
|---|-------|---------|-----------|
| 1 | EIP-712 domain separator / chain ID replay | Not exploitable | `domainSeparator` computed with `chainid()` and `address(this)` in GPv2Signing constructor. The auction uses `i_gpV2Settlement.domainSeparator()`. No cross-chain replay possible. |
| 2 | Fake GPv2 Settlement contract | Not exploitable | `i_gpV2Settlement` is immutable, set in constructor. Only the real settlement's domainSeparator is used for order hash verification. |
| 3 | ERC777/ERC4626 reentrancy via balanceOf | Not exploitable | `s_entered` guard protects both `bid()` and `isValidSignature`. Non-canonical ERC20s are OOS per protocol docs. |
| 4 | Integer truncation int192 -> uint224 | Not exploitable | int192 max (~3.1e57) scaled to 18 decimals fits in uint224 (~2.7e67) for any realistic price. SafeCast reverts on overflow. |
| 5 | Malicious token behavior | OOS | Protocol chooses tokens via admin allowlist. SafeERC20 handles non-standard returns. |
| 6 | Block timestamp manipulation | Negligible impact | Validators can shift ~12 seconds. Dutch auction curves are typically over hours. 12s impact on price is negligible. |
| 7 | Stale performData | Already handled | `performUpkeep` re-validates prices, minimum sizes, and auction existence. Stale data causes revert, not loss. |
| 8 | Self-referential auction (asset == assetOut) | Not possible | `performUpkeep` line 350: if asset == assetOut, transfers directly to receiver instead of starting auction. |
| 9 | Precision loss accumulation | Not exploitable | Solady `mulDivUp` uses 512-bit intermediate. Rounding consistently favors protocol (rounds UP the amount bidder pays). |
| 10 | Admin withdraw during active auction | Not exploitable | `emergencyWithdraw` requires `whenPaused`. When paused, `isValidSignature` also reverts (`whenNotPaused`), preventing CowSwap execution. |
| 11 | transmit() price rollback (older report overwrites newer) | Requires trusted role | PRICE_ADMIN is trusted. No monotonicity check exists but the role is OOS. |
| 12 | bid() missing slippage protection | Already found (M-06) | Confirmed in audit state file as existing finding. |
| 13 | performUpkeep missing auction end validation | Already found (M-04) | Confirmed in audit state file as existing finding. |
| 14 | Duplicate assets in performData | Self-protecting | Second iteration reverts due to `LiveAuction` check (for eligible) or `InvalidAuction` (for ended). |
| 15 | checkUpkeep gas DoS | Already found (M-12) | Confirmed in audit state file as existing finding. |
| 16 | L2 sequencer downtime | Already found (M-13) | Confirmed in audit state file as existing finding. |
| 17 | WorkflowRouter selector extraction | Not exploitable | Solidity 0.8 properly masks bytes4 after inline assembly. Short data produces garbage selector that won't match allowlist. |
| 18 | `_getAssetOutAmount` returning 0 | Not possible | With validated non-zero inputs and `mulDivUp` rounding, minimum return is 1 unit of assetOut. |
| 19 | `s_assetParams[s_assetOut].decimals == 0` during bid | Not possible | AssetOut params can't be removed during live auctions (enforced by `_applyAssetParamsUpdates`). Auctions can only start when assetOut is configured (`whenAssetOutConfigured` on `performUpkeep`). |
| 20 | Cross-auction order reuse (old CowSwap order on new auction) | Self-protecting | `isValidSignature` re-validates at settlement time: new auction start = new elapsed time = new minBuyAmount. Old order's buyAmount unlikely to meet new starting price. |

---

## Files Analyzed

- `C:/Users/shieru_k/Documents/security-agent/2026-03-chainlink/src/GPV2CompatibleAuction.sol` (197 lines)
- `C:/Users/shieru_k/Documents/security-agent/2026-03-chainlink/src/BaseAuction.sol` (812 lines)
- `C:/Users/shieru_k/Documents/security-agent/2026-03-chainlink/src/PriceManager.sol` (428 lines)
- `C:/Users/shieru_k/Documents/security-agent/2026-03-chainlink/src/AuctionBidder.sol` (215 lines)
- `C:/Users/shieru_k/Documents/security-agent/2026-03-chainlink/src/EmergencyWithdrawer.sol` (113 lines)
- `C:/Users/shieru_k/Documents/security-agent/2026-03-chainlink/src/FeeAggregator.sol` (455 lines)
- `C:/Users/shieru_k/Documents/security-agent/2026-03-chainlink/src/WorkflowRouter.sol` (330 lines)
- `C:/Users/shieru_k/Documents/security-agent/2026-03-chainlink/src/Caller.sol` (65 lines)
- `C:/Users/shieru_k/Documents/security-agent/2026-03-chainlink/src/PausableWithAccessControl.sol` (100 lines)
- `C:/Users/shieru_k/Documents/security-agent/2026-03-chainlink/src/vendor/@cowprotocol/contracts/src/contracts/libraries/GPv2Order.sol` (234 lines)
- `C:/Users/shieru_k/Documents/security-agent/2026-03-chainlink/src/vendor/@cowprotocol/contracts/src/contracts/mixins/GPv2Signing.sol` (307 lines)
- `C:/Users/shieru_k/Documents/security-agent/2026-03-chainlink/src/libraries/Roles.sol`
- `C:/Users/shieru_k/Documents/security-agent/2026-03-chainlink/src/libraries/Errors.sol`
- `C:/Users/shieru_k/Documents/security-agent/2026-03-chainlink/src/interfaces/IBaseAuction.sol`
- Keystone `KeystoneForwarder.sol` (for WorkflowRouter metadata format verification)
