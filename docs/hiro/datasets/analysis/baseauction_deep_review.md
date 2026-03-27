# BaseAuction.sol Deep Security Review

Source: `C:/Users/shieru_k/Documents/security-agent/2026-03-chainlink/src/BaseAuction.sol`

Trust model: DEFAULT_ADMIN_ROLE / AUCTION_WORKER_ROLE = trusted. `bid()` callers = untrusted.

---

## Finding 1: Direct Token Transfers Inflate availableBalance, Enabling Bidding Beyond Auctioned Amount (Medium)

**Location:** `bid()` L437, `checkUpkeep()` L247-248

**Description:**
`availableBalance` at L437 is computed as `IERC20(asset).balanceOf(address(this))`. This includes not only the tokens pulled from the FeeAggregator during `performUpkeep`, but also any tokens sent directly to the contract (donations, accidental transfers, or prior auction leftovers from other auctions of the same token).

When an auction starts at L321, `transferForSwap` pulls a specific amount from the FeeAggregator. But `bid()` allows bidders to purchase up to the full `balanceOf(address(this))` of that token. If extra tokens of the same asset are sitting in the contract (e.g., from a previous auction that was not fully drained, or from direct transfers), the bidder can buy more tokens than were intended for auction, at the auction's discounted price.

Crucially, the `_getAssetOutAmount` calculation at L442 uses the user-supplied `amount` (capped to `availableBalance`), so the bidder pays the auction-curve-discounted rate for tokens that were never intended to be auctioned.

**Impact:** An attacker can send tokens directly to the contract before/during an auction to inflate the available pool. While this seems like it costs the attacker, the tokens were obtained at market rate but the bidder (possibly the same attacker) buys them back at a discounted auction price. The net benefit depends on the current price multiplier vs. 1.0. When `priceMultiplier < 1e18` (discount phase), the attacker gets tokens cheaper than they donated them -- this is a net loss for the attacker. When `priceMultiplier > 1e18` (premium phase), there is no economic exploit. However, for *other* parties' tokens that land in the contract (e.g., tokens mistakenly sent), any bidder can purchase them at the auction discount, which constitutes a loss for the sender.

More importantly, `checkUpkeep()` at L247-251 uses `balanceOf(address(this))` to check if an auction should end early (dust check). Direct token deposits to the contract can prevent auctions from being ended early, extending them beyond what the protocol intends.

**Severity: Low-Medium.** Direct token transfers are an edge case but the impact on auction ending logic is a concrete griefing vector.

---

## Finding 2: Fee-on-Transfer Tokens Cause Underpayment in bid() (Medium)

**Location:** `bid()` L453

**Description:**
At L453, `IERC20(assetOut).safeTransferFrom(msg.sender, address(this), assetOutAmount)` pulls the computed `assetOutAmount` from the bidder. If `assetOut` is a fee-on-transfer token, the contract receives less than `assetOutAmount`. However, the contract's accounting does not verify the received balance delta.

The auction sends the full requested `amount` of the auctioned token to the bidder at L444 *before* pulling assetOut at L453. Even though SafeERC20 ensures the `transferFrom` call succeeds, the contract ends up with fewer assetOut tokens than it computed as the fair value of the trade.

When `_onAuctionEnd` later transfers assetOut to `s_assetOutReceiver` at L393-396, the receiver gets less than the cumulative auction value.

**Precondition:** `s_assetOut` must be a fee-on-transfer token. The contract does not explicitly restrict this.

**Severity: Medium** if fee-on-transfer tokens are in scope. The auction's price curve guarantees break down because the protocol systematically receives less assetOut than computed. Over multiple bids, the shortfall compounds.

---

## Finding 3: Rebase Token Incompatibility in bid() Transfer (Low)

**Location:** `bid()` L444

**Description:**
At L444, `IERC20(asset).safeTransfer(msg.sender, amount)` transfers the auctioned asset. If the asset is a positive-rebase token, the contract's `balanceOf` may have increased since the auction started, meaning `availableBalance` at L437 includes rebased amounts. This is conceptually similar to Finding 1 but triggered automatically.

For negative-rebase tokens, the `balanceOf` may have decreased below what was originally pulled from the FeeAggregator. This could cause a scenario where the `amount` cap at L438 restricts bids more than expected, but the `assetOutAmount` computation at L442 is based on the original price data, so there is no direct accounting mismatch -- just reduced auction throughput.

**Severity: Low.** Rebase tokens are an explicit design assumption that most auction protocols do not support. This is informational unless the protocol explicitly intends to support rebase tokens.

---

## Finding 4: checkUpkeep Uses Unvalidated Price for Auction Ending Decision (Medium)

**Location:** `checkUpkeep()` L238, L248-251

**Description:**
At L238, `_getAssetPrice(asset, false)` is called with `withValidation = false`. The returned `assetPrice` may be zero or stale. This price is then used at L248 to compute `assetBalanceUsdValue`:

```solidity
uint256 assetBalanceUsdValue = (assetBalance * assetPrice) / (10 ** assetParams.decimals);
```

If `assetPrice` is zero (stale Data Streams + no fallback Data Feed configured), then `assetBalanceUsdValue` will be zero regardless of actual balance. The condition at L249-251 checks:

```solidity
auctionStart + assetParams.auctionDuration < block.timestamp
    || (isPriceValid && assetBalanceUsdValue < assetParams.minAuctionSizeUsd)
```

The second branch is gated by `isPriceValid`, so a zero/stale price alone does not trigger early auction ending through the USD value check. However, if `isPriceValid` is true but the price is *manipulated* (e.g., a stale but still within-threshold Data Streams price that is artificially low), the auction could be ended early due to the USD value appearing below `minAuctionSizeUsd`.

The first branch (`auctionStart + assetParams.auctionDuration < block.timestamp`) uses strict `<` instead of `<=`. This means that exactly at `auctionStart + auctionDuration`, the auction is NOT considered ended by `checkUpkeep`, but `bid()` at L425 uses `>` (`elapsedTime > assetParams.auctionDuration`), which means `bid()` would also consider it valid at exactly the boundary. This is consistent but worth noting.

**More critically:** Even though the price-based early-end is guarded by `isPriceValid`, the `assetPrice` used for the USD value computation at L248 could be stale *within* the staleness threshold. A price that is valid but significantly outdated (just under the threshold) could misrepresent the actual USD value, triggering an incorrect early auction end.

**Severity: Low.** The `isPriceValid` guard mitigates the zero-price case. The stale-but-valid price is an inherent oracle limitation.

---

## Finding 5: performUpkeep Duplicate Asset in eligibleAssets Causes Double Auction Start Revert (Low)

**Location:** `performUpkeep()` L324-330

**Description:**
If `performData` contains the same asset twice in `eligibleAssets`, the first iteration sets `s_auctionStarts[asset] = block.timestamp` at L353. The second iteration hits the check at L327-328 (`s_auctionStarts[asset] != 0`) and reverts with `LiveAuction()`.

This is not exploitable because `performData` is constructed by `checkUpkeep` (which iterates an EnumerableSet that cannot contain duplicates) and is submitted by a trusted AUCTION_WORKER_ROLE. However, if a worker manually constructs malformed `performData`, the entire transaction reverts, preventing any other legitimate auction operations in the same batch from executing.

**Severity: Low.** Requires trusted-role operator error.

---

## Finding 6: _getAssetOutAmount Division by Zero When auctionDuration is Zero (Low)

**Location:** `_getAssetOutAmount()` L785, L795

**Description:**
At L795, `mulDiv(elapsedTime, assetInParams.auctionDuration)` divides by `auctionDuration`. If `auctionDuration` is 0, this would be a division by zero, causing a revert.

However, `_applyAssetParamsUpdates` at L647 enforces `auctionDuration != 0` for non-assetOut assets. For `assetOut`, the auction duration check is skipped (L646: `if (asset != s_assetOut)`), but `assetOut` is never actually auctioned via `bid()` -- when `assetOut` appears in `eligibleAssets` during `performUpkeep`, it is handled by a direct transfer at L351 rather than starting an auction.

This means `_getAssetOutAmount` should never be called for `assetOut`, and for all other assets, `auctionDuration > 0` is enforced.

**Severity: Non-issue.** The validation correctly prevents this scenario.

---

## Finding 7: startingPriceMultiplier == endingPriceMultiplier Edge Case (Informational)

**Location:** `_getAssetOutAmount()` L793-795, `_applyAssetParamsUpdates()` L653

**Description:**
The validation at L653 checks `endingPriceMultiplier > startingPriceMultiplier` but allows equality. When `startingPriceMultiplier == endingPriceMultiplier`, the `mulDiv` at L795 computes `(0).mulDiv(elapsedTime, auctionDuration)` which equals 0. So `priceMultiplier = startingPriceMultiplier - 0 = startingPriceMultiplier`. This is correct -- a flat price curve. No issue.

**Severity: Non-issue.** Works correctly.

---

## Finding 8: _onAuctionEnd Transfers All assetOut Balance Including From Other Auctions (Medium)

**Location:** `_onAuctionEnd()` L393-396

**Description:**
When an auction ends, `_onAuctionEnd` at L393-396 transfers the *entire* `assetOut` balance to `assetOutReceiver`:

```solidity
uint256 assetOutBalance = IERC20(s_assetOut).balanceOf(address(this));
if (assetOutBalance > 0) {
    IERC20(s_assetOut).safeTransfer(s_assetOutReceiver, assetOutBalance);
}
```

If multiple auctions are running concurrently (for different assets), and bidders have been paying `assetOut` into the contract for different auctions, ending *one* auction sweeps the `assetOut` accumulated from *all* ongoing auctions to the receiver. This is not a loss (the receiver is the intended destination), but it means the contract's `assetOut` balance is zeroed out even for still-active auctions. This is actually fine because `assetOut` is not tracked per-auction -- the contract holds it in aggregate and forwards it all to the receiver.

However, there is a subtle interaction with `performUpkeep`: at L350-351, when `assetOut` itself is in `eligibleAssets`, the entire balance is transferred to `assetOutReceiver`. If this happens in the same transaction as other auction starts, and those auctions have already received bids in a previous block, the bid-accumulated `assetOut` is swept along with the FeeAggregator-pulled `assetOut`.

**Severity: Non-issue by design.** The receiver is meant to receive all assetOut. The forward-all pattern is intentional.

---

## Finding 9: _onAuctionEnd Reverts If feeAggregator or assetOutReceiver Blocks Transfers (Low)

**Location:** `_onAuctionEnd()` L388-396

**Description:**
At L390, unsold auction tokens are transferred back to the FeeAggregator via `safeTransfer`. If the FeeAggregator contract is paused, has been upgraded to reject incoming transfers, or is a contract that reverts on `transfer()`, this call reverts, preventing the auction from being ended.

Similarly, at L395, if `s_assetOutReceiver` is a contract that reverts on token receipt, the auction cannot be ended.

This creates a denial-of-service where auctions cannot be cleanly ended. The `endedAuctions` array in `performUpkeep` processes all ended auctions in a loop (L359-369), so one failing `_onAuctionEnd` reverts the entire batch, also preventing other auctions from being ended or new auctions from starting (since they are in the same transaction).

**Mitigation consideration:** The admin can change `feeAggregator` and `assetOutReceiver` via `setFeeAggregator` and `setAssetOutReceiver`, but both are guarded by `_whenNoLiveAuctions()`. If there ARE live auctions that cannot end because of the revert, and the config cannot be changed because of live auctions, the system is deadlocked. The only escape is `emergencyWithdraw` (from EmergencyWithdrawer) or pausing.

**Severity: Low.** Requires a blocklisted/paused receiver, but the deadlock scenario is worth noting.

---

## Finding 10: Intermediate Overflow in mulDivUp Chain (Informational)

**Location:** `_getAssetOutAmount()` L799

**Description:**
L799 computes:
```solidity
uint256 auctionUsdValue = amountIn.mulDivUp(assetInUsdPrice, 10 ** assetInParams.decimals).mulWadUp(priceMultiplier);
```

Solady's `mulDivUp` uses assembly with `mul`/`div` and handles intermediate overflow via the 512-bit multiplication pattern. Specifically, it computes `(a * b + d - 1) / d` with proper overflow handling. So intermediate overflow of `amountIn * assetInUsdPrice` is handled correctly by Solady's implementation.

The subsequent `mulWadUp(priceMultiplier)` is `mulDivUp(result, priceMultiplier, 1e18)`, also overflow-safe.

At L802, `auctionUsdValue.mulDivUp(10 ** s_assetParams[s_assetOut].decimals, assetOutUsdPrice)` is also overflow-safe.

**Severity: Non-issue.** Solady handles intermediate overflow correctly.

---

## Finding 11: Very Small assetOutUsdPrice Causes Inflated Output Amount (Low)

**Location:** `_getAssetOutAmount()` L802

**Description:**
At L802:
```solidity
return auctionUsdValue.mulDivUp(10 ** s_assetParams[s_assetOut].decimals, assetOutUsdPrice);
```

If `assetOutUsdPrice` is very small (e.g., 1 wei = $0.000000000000000001), the division produces an enormously inflated `assetOutAmount`. The bidder would need to pay this inflated amount in `assetOut` tokens, so at first glance this seems like it hurts the bidder.

However, the issue is that `assetOutUsdPrice` is fetched with `withValidation = true` in the `bid()` path (L798 -> L429's call chain), which ensures it is non-zero and non-stale. But it does not validate that the price is *reasonable*. A manipulated oracle that reports a price of 1 (smallest non-zero value, representing $0.000000000000000001) would make each unit of auctioned asset require an astronomical amount of `assetOut`, effectively bricking the auction.

Conversely, if the oracle is manipulated to report an extremely high `assetOutUsdPrice`, the `assetOutAmount` becomes very small. The bidder could then acquire auctioned tokens for almost free.

**Severity: Low.** This is an oracle manipulation attack, and the protocol relies on Chainlink Data Streams + Data Feeds, which are generally resistant to manipulation. But worth documenting the attack surface.

---

## Finding 12: minBidUsdValue Can Be Changed During Active Auctions (Low)

**Location:** `_setMinBidUsdValue()` L474-486, `setMinBidUsdValue()` L466-470

**Description:**
`setMinBidUsdValue` has no `_whenNoLiveAuctions()` check. It can be called by `ASSET_ADMIN_ROLE` at any time, including during active auctions. If `minBidUsdValue` is increased during an auction, bids that were previously valid may now be rejected. If decreased, previously-rejected small bids become valid.

For the GPV2CompatibleAuction subcontract, CowSwap orders signed by the `isValidSignature` flow may have been created based on a previous `minBidUsdValue`. Changing it mid-auction could invalidate in-flight CowSwap orders or allow orders that the protocol did not intend.

Note: `minBidUsdValue` is checked in `bid()` at L433, but not in GPV2CompatibleAuction's `isValidSignature`. Let me verify...

Actually, looking at the code, `bid()` does check `minBidUsdValue` at L431-434. The GPV2 `isValidSignature` flow goes through a different path (CowSwap settlement), so `minBidUsdValue` may not apply there (this is related to known M-15 about GPV2 missing minBidUsdValue, so I will not elaborate further).

The core issue: changing `minBidUsdValue` during active auctions can DOS existing bidders if increased significantly. This is acceptable given `ASSET_ADMIN_ROLE` is trusted, but it is a configuration hygiene concern.

**Severity: Low.** Trusted admin action, but no guard prevents mid-auction changes that could disrupt bidding.

---

## Finding 13: Gas Exhaustion via Large Allowlisted Asset Set in checkUpkeep (Low)

**Location:** `checkUpkeep()` L228, `_liveAuctionExists()` L677

**Description:**
`checkUpkeep` iterates over all `s_allowlistedAssets.values()` at L228. For each asset, it:
1. Reads `s_assetParams` from storage
2. Calls `_getAssetPrice` which reads `s_dataStreamsPrice` and potentially makes an external call to `feedInfo.usdDataFeed.latestRoundData()`
3. Calls `IERC20(asset).balanceOf(address(this))` (external call)
4. Possibly calls `IERC20(asset).balanceOf(feeAggregator)` (external call)

Each iteration involves 2-3 external calls plus multiple storage reads. With a large number of allowlisted assets (e.g., 100+), `checkUpkeep` could exceed the block gas limit, especially since it is a `view` function that Chainlink Automation calls off-chain but with gas limits.

Similarly, `_liveAuctionExists()` at L677 iterates all allowlisted assets. Since `_whenNoLiveAuctions()` uses this, configuration changes also become expensive.

**Severity: Low.** Administrative concern. The number of allowlisted assets is controlled by trusted admins.

---

## Finding 14: performUpkeep assetOut Handling -- Race Between checkUpkeep and performUpkeep (Low)

**Location:** `performUpkeep()` L350-351

**Description:**
In `checkUpkeep`, the `s_assetOut` address is read and used to determine if an asset in the iteration matches `assetOut`. In `performUpkeep`, at L350, the same check is done against the *current* `s_assetOut`.

If `s_assetOut` were changed between `checkUpkeep` and `performUpkeep` (via `setAssetOut`), an asset that was treated as `assetOut` in `checkUpkeep` would not be treated as such in `performUpkeep`, and vice versa. This could lead to:
- An asset that should have been directly transferred to the receiver instead getting an auction started
- An asset that should have had an auction started instead getting directly transferred

However, `_setAssetOut` calls `_whenNoLiveAuctions()`, preventing changes during active auctions. If `checkUpkeep` returns eligible assets (meaning no auctions are currently live for those assets), and an admin calls `setAssetOut` before `performUpkeep` executes, the race is possible but only in a narrow window and requires deliberate admin action.

**Severity: Low.** Requires admin action in a narrow timing window during which the AUCTION_WORKER also submits a transaction.

---

## Summary of New Findings

| ID | Severity | Title |
|----|----------|-------|
| F-01 | Low-Medium | Direct token transfers inflate availableBalance and can grief auction ending |
| F-02 | Medium | Fee-on-transfer assetOut causes systematic underpayment |
| F-03 | Low | Rebase token incompatibility |
| F-04 | Low | checkUpkeep uses potentially stale-but-valid prices for ending decisions |
| F-05 | Low | Duplicate asset in performData reverts entire batch |
| F-06 | Non-issue | auctionDuration == 0 division by zero (properly guarded) |
| F-07 | Non-issue | Equal price multipliers (works correctly) |
| F-08 | Non-issue | All assetOut swept on any auction end (by design) |
| F-09 | Low | Receiver revert causes deadlock (cannot end auctions AND cannot change config) |
| F-10 | Non-issue | Intermediate overflow in mulDivUp (handled by Solady) |
| F-11 | Low | Extreme oracle prices cause inflated/deflated assetOutAmount |
| F-12 | Low | minBidUsdValue changeable during active auctions |
| F-13 | Low | Gas exhaustion with large allowlisted asset set |
| F-14 | Low | checkUpkeep/performUpkeep race on assetOut change |

### Key Actionable Findings

**F-02 (Fee-on-Transfer):** If `assetOut` is ever a fee-on-transfer token, the contract systematically receives less than the computed auction price. Consider adding a balance-before/after check in `bid()` or explicitly documenting that fee-on-transfer tokens are unsupported as `assetOut`.

**F-09 (Deadlock):** If `feeAggregator` or `assetOutReceiver` blocks transfers, auctions cannot end, and config cannot be changed because live auctions exist. Consider adding a mechanism to force-end auctions or allowing config changes even with live auctions in emergency scenarios (beyond `emergencyWithdraw`).

**F-01 (Direct Transfers):** Tokens sent directly to the contract become available at auction discount. Consider tracking the expected auction balance per asset rather than using `balanceOf`.
