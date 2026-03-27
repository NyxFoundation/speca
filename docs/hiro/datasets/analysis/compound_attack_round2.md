# Compound Attack Analysis - Round 2

## Target: Chainlink Payment Abstraction V2
## Date: 2026-03-27

---

## Methodology

Each of the 10 compound scenarios was traced step-by-step against the actual source code in `src/`. Findings are classified as VALID (new exploitable compound attack), AMPLIFIES (extends a known finding), or INVALID (disproven by code).

---

## Scenario 1: CowSwap + Direct Bid Race

**Status: INVALID**

**Analysis:**
- `_onAuctionStart` (GPV2CompatibleAuction.sol:92) sets approval to `IERC20(asset).balanceOf(address(this))` at auction start.
- If a direct `bid()` executes first, it calls `IERC20(asset).safeTransfer(msg.sender, amount)` (BaseAuction.sol:444), reducing the contract's balance.
- The CowSwap vault relayer still holds the original (higher) approval amount.
- However, `transferFrom` is limited by `min(allowance, balance)`. Since balance decreased, the relayer cannot transfer more than the remaining balance.
- `isValidSignature` (GPV2CompatibleAuction.sol:144-146) checks `order.sellAmount > assetInBalance` at validation time, so any CowSwap order exceeding remaining balance will fail validation.

**Conclusion:** The approval exceeding balance is not exploitable. ERC20 `transferFrom` semantics prevent over-transfer, and `isValidSignature` re-checks balance at settlement time.

---

## Scenario 2: Price Oracle + Auction Timing

**Status: INVALID**

**Analysis:**
- `checkUpkeep` calls `_getAssetPrice(asset, false)` (BaseAuction.sol:238) -- no validation, silently returns stale/zero prices.
- `performUpkeep` calls `_getAssetPrice(asset, true)` (BaseAuction.sol:315, 342) -- with validation, reverts on stale/zero prices.
- If price goes stale between `checkUpkeep` and `performUpkeep`, `performUpkeep` reverts. No auction starts with stale data.
- For auction ending: duration-based end (line 250: `auctionStart + assetParams.auctionDuration < block.timestamp`) does NOT require valid price. Balance-based end (line 251) requires `isPriceValid`. If price is stale, only duration-based end triggers, which is correct behavior.
- `bid()` always validates prices (line 429: `_getAssetPrice(asset, true)`), so bids cannot use stale prices.

**Conclusion:** The system correctly handles stale prices. `performUpkeep` reverts if prices became stale after `checkUpkeep`, and `bid()` always validates. No permissionless actor can exploit this timing gap.

---

## Scenario 3: Multiple Auction Interaction

**Status: INVALID**

**Analysis:**
- `_onAuctionEnd` (BaseAuction.sol:393-396) transfers ALL `assetOut` balance to `s_assetOutReceiver`:
  ```solidity
  uint256 assetOutBalance = IERC20(s_assetOut).balanceOf(address(this));
  if (assetOutBalance > 0) {
      IERC20(s_assetOut).safeTransfer(s_assetOutReceiver, assetOutBalance);
  }
  ```
- If auctions for Asset A and Asset B are both active, and bids on both deposit assetOut, ending Auction A sweeps ALL assetOut (including what was paid for Auction B bids).
- When Auction B later ends, there may be 0 assetOut left to sweep.
- However, the net effect is identical: `s_assetOutReceiver` receives the same total assetOut regardless of sweep order.
- No pricing interaction exists between auctions -- each auction's price is computed independently from its own `assetParams`, `assetPrice`, and `elapsedTime`.

**Conclusion:** Ending one auction does not affect another's pricing. The assetOut sweep order is cosmetically different but produces the same net outcome for the receiver.

---

## Scenario 4: AuctionBidder + Token Approval Chain

**Status: ALREADY KNOWN (H-01)**

**Analysis:**
- `AuctionBidder.auctionCallback` (AuctionBidder.sol:107-109) decodes `data` as `Call[]` and passes to `_multiCall`.
- `_multiCall` (Caller.sol:49-63) performs arbitrary low-level calls with no target restrictions.
- This is precisely H-01. No additional contracts in the chain beyond what H-01 covers add new attack surface.
- The `BaseAuction.bid()` function (BaseAuction.sol:448-449) calls `IAuctionCallback(msg.sender).auctionCallback(...)` with `msg.sender` being the AuctionBidder. The callback origin is verified at AuctionBidder.sol:103.

**Conclusion:** Subsumed by H-01. The `_multiCall` unrestricted call is the root cause.

---

## Scenario 5: Dutch Auction Price + CowSwap Partial Fill

**Status: INVALID**

**Analysis:**
- CowSwap orders are created as `partiallyFillable = true` (enforced at GPV2CompatibleAuction.sol:168-169).
- `isValidSignature` validates the FULL order parameters (sellAmount, buyAmount) each time it is called.
- At time T, order is created with `buyAmount = X` (matching T's auction price with premium).
- At time T+N, price has decayed, so `minBuyAmount` at T+N is lower than at T.
- The check `order.buyAmount < minBuyAmount` (line 155) passes MORE easily at T+N because minBuyAmount decreased while order.buyAmount stayed the same.
- For partial fills, CowSwap's settlement contract enforces proportional execution: if filling P% of sellAmount, it transfers P% of buyAmount. The `isValidSignature` check is against total amounts, not partial amounts.
- The auction contract receives proportionally MORE assetOut than the current minBuyAmount requires (since the order was priced at the earlier, higher rate).

**Conclusion:** Partial fills at later times are favorable to the auction contract (it receives more than minimum). No exploit exists -- the solver gets a worse deal over time, not a better one.

---

## Scenario 6: Balance Manipulation + Auction End

**Status: INVALID (Low/Informational -- griefing only)**

**Analysis:**
- Sending tokens directly to the auction contract increases `balanceOf(address(this))`.
- `bid()` (BaseAuction.sol:437): `availableBalance = IERC20(asset).balanceOf(address(this))` -- more tokens available for bidding.
- `checkUpkeep` (BaseAuction.sol:247-251): balance-based auction end check uses `assetBalance = IERC20(asset).balanceOf(address(this))`. Donating tokens keeps `assetBalanceUsdValue >= assetParams.minAuctionSizeUsd`, preventing early end.
- `_onAuctionStart` (GPV2CompatibleAuction.sol:92): CowSwap approval set to balance at start time. Tokens sent AFTER start are NOT approved to the vault relayer, but ARE available via `bid()`.
- `_onAuctionEnd` (BaseAuction.sol:388-391): ALL remaining balance sent to feeAggregator. Donated tokens are absorbed.

**Conclusion:** Direct token transfers can delay auction end (griefing) and the donated tokens are absorbed into the feeAggregator. No fund loss for the protocol. The attacker loses their donated tokens. This is at most informational-level griefing.

---

## Scenario 7: assetOutReceiver Change Mid-Auction

**Status: INVALID**

**Analysis:**
- `_setAssetOutReceiver` (BaseAuction.sol:531-543) calls `_whenNoLiveAuctions()` at line 534.
- `_whenNoLiveAuctions()` (BaseAuction.sol:668-672) iterates all allowlisted assets and reverts if any has `s_auctionStarts[asset] != 0`.

**Conclusion:** Cannot change `assetOutReceiver` during any live auction. Properly guarded.

---

## Scenario 8: Feed Info Update + Active Auction

**Status: INVALID**

**Analysis:**
- `_onFeedInfoUpdate` override in BaseAuction (line 688-697):
  ```solidity
  if ((asset == s_assetOut && _liveAuctionExists()) || s_auctionStarts[asset] != 0) {
      revert LiveAuction();
  }
  ```
- For the actively auctioned asset: `s_auctionStarts[asset] != 0` is true, so update reverts.
- For assetOut: if any auction is live, update reverts.
- For a different non-auctioned asset: update IS allowed during another asset's auction. But this doesn't affect the active auction's pricing at all -- each auction uses its own asset's feed info.

**Conclusion:** Feed info for actively auctioned assets and assetOut cannot be changed mid-auction. Updating feed info for unrelated assets has no impact on active auctions.

---

## Scenario 9: MinBidUsdValue Change Mid-Auction (Amplifies M-15)

**Status: AMPLIFIES M-15 (but requires trusted admin action)**

**Analysis:**
- `setMinBidUsdValue` (BaseAuction.sol:466-470) has `onlyRole(Roles.ASSET_ADMIN_ROLE)` but NO `_whenNoLiveAuctions()` check.
- `bid()` (BaseAuction.sol:431-434) checks: `if (bidUsdValue < minBidUsdValue) revert BidValueTooLow(...)`.
- `isValidSignature` (GPV2CompatibleAuction.sol:119-176) does NOT check `minBidUsdValue` at all.
- If admin sets `minBidUsdValue` to `type(uint88).max` during an active auction:
  - All direct `bid()` calls revert (any realistic bid value < max uint88).
  - CowSwap settlement via `isValidSignature` still works (no minBidUsdValue check).
  - This creates an asymmetry: CowSwap becomes the ONLY settlement path.
- Combined with M-15 (minBid bypass via GPV2), this means an admin action can funnel all settlement through CowSwap exclusively.

**However:** This requires a trusted ASSET_ADMIN_ROLE to act maliciously or accidentally. Under the trust model where admin roles are trusted, this is not an external attack. The missing `_whenNoLiveAuctions()` guard on `setMinBidUsdValue` is a design inconsistency but not exploitable without trusted role compromise.

**Missing guard location:** `BaseAuction.sol:466-470` -- `setMinBidUsdValue` lacks `_whenNoLiveAuctions()`.

**Conclusion:** This is a valid code-level inconsistency (other auction-sensitive config changes DO have `_whenNoLiveAuctions` guards) that amplifies M-15, but it requires a trusted admin role to trigger. Severity: Low (design inconsistency) unless admin trust model is relaxed.

---

## Scenario 10: EnumerableSet + checkUpkeep Gas

**Status: INVALID (operational concern, not security vulnerability)**

**Analysis:**
- `checkUpkeep` (BaseAuction.sol:220): `address[] memory auctions = s_allowlistedAssets.values()` copies all addresses to memory, then iterates.
- Each iteration: reads `s_assetParams[asset]` (SLOAD), calls `_getAssetPrice(asset, false)` (potentially 2 external calls: data streams price SLOAD + `usdDataFeed.latestRoundData()`), calls `IERC20(asset).balanceOf(...)` (external call).
- Estimated gas per asset: ~10,000-30,000 gas depending on price source.
- Block gas limit (Ethereum): 30M gas. This allows ~1,000-3,000 assets before gas limit.
- `_liveAuctionExists()` (line 676-683) also iterates all assets but only does SLOADs (~2,100 gas per iteration), allowing ~14,000 assets.
- `checkUpkeep` is a `view` function typically called off-chain by Chainlink Automation. Off-chain calls have no gas limit enforcement (uses `eth_call`).
- Even if called on-chain (e.g., by another contract), the practical number of allowlisted assets is unlikely to exceed a few hundred.

**Conclusion:** Not a practical security vulnerability. The number of allowlisted assets is controlled by `ASSET_ADMIN_ROLE`, and `checkUpkeep` is designed for off-chain execution. On-chain gas exhaustion would require thousands of assets, which is operationally unrealistic.

---

## Summary of Results

| # | Scenario | Status | New Finding? |
|---|----------|--------|-------------|
| 1 | CowSwap + Direct Bid Race | INVALID | No |
| 2 | Price Oracle + Auction Timing | INVALID | No |
| 3 | Multiple Auction Interaction | INVALID | No |
| 4 | AuctionBidder + Token Approval Chain | H-01 | No (known) |
| 5 | Dutch Auction Price + CowSwap Partial Fill | INVALID | No |
| 6 | Balance Manipulation + Auction End | INVALID (Info) | No |
| 7 | assetOutReceiver Change Mid-Auction | INVALID | No |
| 8 | Feed Info Update + Active Auction | INVALID | No |
| 9 | MinBidUsdValue Change Mid-Auction | AMPLIFIES M-15 | Marginal (Low) |
| 10 | EnumerableSet + checkUpkeep Gas | INVALID | No |

## New Finding Detail

### LOW: Missing `_whenNoLiveAuctions` Guard on `setMinBidUsdValue`

**Location:** `BaseAuction.sol:466-470`

**Description:** `setMinBidUsdValue()` can be called during active auctions, unlike other auction-sensitive configuration functions (`setAssetOut`, `setAssetOutReceiver`, `setFeeAggregator`, `applyAssetParamsUpdates` for active assets) which all require `_whenNoLiveAuctions()`. This inconsistency allows the ASSET_ADMIN_ROLE to change the minimum bid threshold mid-auction, potentially blocking all direct `bid()` calls while CowSwap settlement remains unaffected (since `isValidSignature` does not check `minBidUsdValue`).

**Impact:** Low. Requires trusted admin role. The asymmetry between `bid()` and `isValidSignature` minBid checking is already captured by M-15; this finding shows that the window can be opened/widened by admin action during a live auction.

**Recommendation:** Add `_whenNoLiveAuctions()` check to `setMinBidUsdValue()` for consistency with other configuration setters, or add `minBidUsdValue` validation to `isValidSignature`.
