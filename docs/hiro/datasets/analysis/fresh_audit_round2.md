# Fresh Audit Round 2 - Chainlink Payment Abstraction V2

**Auditor:** Claude Opus 4.6 (Senior Smart Contract Security Auditor)
**Date:** 2026-03-27
**Scope:** GPV2CompatibleAuction.sol, BaseAuction.sol, PriceManager.sol, AuctionBidder.sol, and supporting contracts

---

## [MEDIUM] CowSwap order `validTo` not bounded to auction end time -- stale order can settle on a new auction at a stale price

**File:** `src/GPV2CompatibleAuction.sol:148-160`

**Description:**
In `isValidSignature()`, the `validTo` field of the GPv2Order is only checked for basic expiry (`order.validTo < block.timestamp`). There is no validation that `validTo <= auctionStart + auctionDuration`. While `isValidSignature()` does independently check whether the current elapsed time exceeds `auctionDuration` (line 150), there is a concrete scenario where this gap matters:

1. Auction A starts at time T for token X, with `auctionDuration = 3600`.
2. A CowSwap solver creates an order with `validTo = T + 7200` (2 hours, well beyond auction end) and `buyAmount` set to the minimum at time `T + 3599` (near auction end, maximum discount).
3. Auction A ends at `T + 3600`. `performUpkeep` deletes `s_auctionStarts[X]`.
4. At time `T + 3700`, a NEW Auction B starts for token X. `s_auctionStarts[X] = T + 3700`.
5. At time `T + 3701`, `elapsedTime = 1` (just started). The old order's `buyAmount` was calculated at maximum discount (ending price multiplier). The new auction's price at `elapsedTime=1` uses the `startingPriceMultiplier` (premium), so `minBuyAmount` is HIGH. The old order's `buyAmount` is too low -- **it would be rejected by line 155**.

However, the risk materializes if:
- Auction B has DIFFERENT (more aggressive) price parameters than Auction A
- Or if `startingPriceMultiplier` and `endingPriceMultiplier` are configured close together
- Or at a specific elapsed time in auction B where the decayed price happens to match or fall below the old order's `buyAmount`

In such cases, a stale CowSwap order from Auction A (which was priced at Auction A's parameters) could settle during Auction B, potentially at a price that doesn't reflect Auction B's intended price curve.

**Impact:** A CowSwap order created during one auction could be settleable during a subsequent auction for the same asset, potentially at a price inconsistent with the new auction's intended pricing. This is especially problematic if asset parameters change between auctions. The protocol pays more assetOut than intended by the new auction's price curve.

**PoC sketch:**
1. Configure token X with `startingPriceMultiplier = 1.01e18`, `endingPriceMultiplier = 0.99e18`, `auctionDuration = 3600`
2. Start Auction A. At t=3500 (near end), solver creates order with `buyAmount = minBuyAmount` at 0.99x multiplier, `validTo = now + 7200`
3. Auction A ends. New Auction B starts with same or lower multipliers.
4. At some point during Auction B where multiplier decays to ~0.99x, the old order from Auction A passes `isValidSignature` validation because `buyAmount >= minBuyAmount` at that elapsed time.
5. CowSwap settles the stale order. The order was priced using Auction A's oracle price, but settles using Auction B's price check. If the sell token price changed between auctions, the protocol may overpay.

**Already known?** No. This is distinct from M-14 (stale approval after `_setAuction`) and M-15 (missing minBidUsdValue in isValidSignature). This is about cross-auction order validity.

**Severity rationale:** Medium. Requires specific timing and parameter configurations. The independent `isValidSignature` checks (auction liveness, balance, price) provide defense in depth but don't fully prevent this.

---

## [MEDIUM] `getAssetOutAmount` view function reverts on zero assetOut price despite NatSpec claiming no-revert behavior

**File:** `src/BaseAuction.sol:749-767` and `src/BaseAuction.sol:802`

**Description:**
The `getAssetOutAmount()` external view function's NatSpec states: "This function does not revert but will return zero instead on: Invalid auctions, Stale prices, Invalid timestamp." However, the function CAN revert in two scenarios:

1. **Division by zero when `assetOutUsdPrice = 0`:** The function calls `_getAssetOutAmount(..., false)` which internally calls `_getAssetPrice(s_assetOut, false)` (line 798, withValidation=false). If the assetOut price is zero (no price data), `assetOutUsdPrice = 0`. Then line 802 executes: `auctionUsdValue.mulDivUp(10 ** decimals, 0)` -- division by zero, reverts.

2. **Negative oracle answer:** The NatSpec itself acknowledges "Reverts are still possible if prices fallback to data feeds and return an answer <= 0" -- but the first scenario (zero data streams price with no data feed configured) is NOT acknowledged.

This function is used by `AuctionBidder.bid()` at line 78 when `solution.length == 0`:
```solidity
IERC20(assetOut).forceApprove(address(auction), s_auction.getAssetOutAmount(assetIn, amount, block.timestamp));
```

If `getAssetOutAmount` reverts, the AuctionBidder's simple bid path (without callback) becomes unusable, even though a direct `bid()` call to the auction contract would succeed (it uses `withValidation=true` which reverts with a clear error).

**Impact:** Integrators relying on the documented no-revert behavior of `getAssetOutAmount()` may have their contracts break unexpectedly. The AuctionBidder's simple bid path silently depends on this view function not reverting.

**PoC sketch:**
1. Configure an auction where assetOut's data streams price is zero and no data feed fallback is configured
2. Call `getAssetOutAmount()` for any live auction -- it reverts with a panic (division by zero) rather than returning 0

**Already known?** No. Not in the known findings list.

---

## [LOW] `checkUpkeep` uses uncapped multiplication that can overflow for tokens with 0 decimals and extreme balances

**File:** `src/BaseAuction.sol:248,258`

**Description:**
In `checkUpkeep()`, the USD value calculations use plain Solidity multiplication:

```solidity
uint256 assetBalanceUsdValue = (assetBalance * assetPrice) / (10 ** assetParams.decimals);  // line 248
uint256 availableAssetUsdValue = (availableBalance * assetPrice) / (10 ** assetParams.decimals);  // line 258
```

For a token with 0 decimals (`10 ** 0 = 1`), this simplifies to `assetBalance * assetPrice`. If `assetBalance` and `assetPrice` are both large enough, this multiplication can overflow. While `assetPrice` is scaled to 18 decimals and capped at `uint224`, and typical ERC20 balances are bounded by total supply, a deliberately crafted token with 0 decimals and a very large supply (e.g., `2^200` units) combined with a high price (e.g., `1e18`) would produce an intermediate product exceeding `uint256`.

In contrast, `_getAssetOutAmount()` uses Solady's `mulDivUp` which handles 512-bit intermediates, so `bid()` is safe. The inconsistency means `checkUpkeep` can revert for tokens that `bid()` handles correctly.

Note: `bid()` at line 430 uses the same uncapped pattern: `uint256 bidUsdValue = (amount * assetPrice) / (10 ** assetParams.decimals)`. So `bid()` also has this issue, but the `amount` parameter is bounded by `balanceOf` and the ASSET_ADMIN configures tokens. Still, using `mulDiv` would be more robust.

**Impact:** For extreme token configurations (0 decimals, very large supply), `checkUpkeep` and `bid()` could revert due to overflow, causing DOS. Practically unlikely with standard tokens.

**PoC sketch:**
1. Create a token with 0 decimals and mint `2^200` tokens to the contract
2. Configure price at `1e18` (1 USD)
3. `checkUpkeep()` tries to compute `2^200 * 1e18` which exceeds `uint256.max`

**Already known?** No. Not in the known findings list.

---

## [LOW] `performUpkeep` allows ending an auction that was just started in the same call

**File:** `src/BaseAuction.sol:305-370`

**Description:**
In `performUpkeep()`, the eligible assets loop (lines 324-357) runs before the ended auctions loop (lines 359-369). A caller with AUCTION_WORKER_ROLE (trusted) can craft `performData` that includes the same asset in both `eligibleAssets` and `endedAuctions`:

1. The eligible loop starts the auction: sets `s_auctionStarts[asset] = block.timestamp`, calls `_onAuctionStart(asset)` (which approves the vault relayer).
2. The ended loop processes the same asset: `s_auctionStarts[asset] != 0` passes the check. Calls `_onAuctionEnd(asset)` which transfers all remaining balance back to feeAggregator and revokes the vault relayer approval. Then deletes `s_auctionStarts[asset]`.

Result: Tokens are pulled from feeAggregator and immediately sent back. The auction is started and ended in one transaction without any opportunity for bidding.

While the AUCTION_WORKER_ROLE is trusted, this behavior is unexpected and could be triggered by a misconfigured automation workflow. It also means `checkUpkeep` results cannot be blindly forwarded to `performUpkeep` if there's any delay (though `checkUpkeep` would never produce such overlapping data).

**Impact:** Wasteful gas and unexpected behavior. If automation is misconfigured, tokens could be needlessly round-tripped. No direct loss of funds.

**PoC sketch:**
1. Have token X in feeAggregator with sufficient balance
2. Call `performUpkeep` with `eligibleAssets = [X]` and `endedAuctions = [X]`
3. Tokens are pulled from feeAggregator, approval is set, then tokens are sent back and approval revoked

**Already known?** No. Not in the known findings list. AUCTION_WORKER_ROLE is trusted, so this is Low severity.

---

## [LOW] `_onAuctionEnd` transfers ALL assetOut balance including accumulated bids from other auctions

**File:** `src/BaseAuction.sol:393-396`

**Description:**
When `_onAuctionEnd` is called, it transfers ALL `s_assetOut` balance to `s_assetOutReceiver`:

```solidity
uint256 assetOutBalance = IERC20(s_assetOut).balanceOf(address(this));
if (assetOutBalance > 0) {
    IERC20(s_assetOut).safeTransfer(s_assetOutReceiver, assetOutBalance);
}
```

If multiple auctions are live simultaneously (different tokens), bids on Auction A deposit assetOut into the contract. When Auction B ends, `_onAuctionEnd` sweeps ALL assetOut, including proceeds from Auction A that is still live. While this doesn't cause direct loss (the funds go to the intended receiver), it means:

1. The assetOut balance visible to Auction A bidders drops to 0 between auctions ending
2. If `performUpkeep` processes multiple ended auctions, only the first one actually transfers assetOut (the rest find balance = 0)
3. The accounting of how much assetOut each auction generated is lost

This is by design (the assetOut always goes to the same receiver), but it's worth noting for accounting/monitoring purposes.

**Impact:** No direct fund loss. Assetout proceeds from all auctions are commingled and swept together. Monitoring and accounting become imprecise.

**PoC sketch:**
1. Start auctions for tokens A and B simultaneously
2. Bidders bid on both auctions, depositing assetOut
3. Auction A ends first -- sweeps ALL assetOut including B's proceeds
4. Auction B ends -- finds 0 assetOut to sweep

**Already known?** No. By design but worth documenting.

---

## [INFORMATIONAL] `appData` field in GPv2Order is not validated in `isValidSignature`

**File:** `src/GPV2CompatibleAuction.sol:119-176`

**Description:**
The `isValidSignature()` function validates most fields of the `GPv2Order.Data` struct but does not check the `appData` field (bytes32). While `appData` is primarily used for off-chain metadata (IPFS hash pointing to order metadata), in CowSwap's newer versions it can reference "hooks" -- pre and post-interaction logic. The `appData` value is part of the signed order hash, so different `appData` values produce different order hashes.

A malicious solver could:
1. Create multiple orders with identical parameters but different `appData` values
2. Each order would have a different hash and be independently valid
3. This effectively allows creating multiple valid orders for the same auction

However, since `isValidSignature` checks balance at settlement time (`order.sellAmount > assetInBalance`), only orders up to the available balance can actually settle. Additionally, partial fills mean multiple orders are already expected.

**Impact:** Minimal. Multiple valid orders with different `appData` don't enable any additional value extraction beyond what partial fills already allow.

**Already known?** No. Informational only.

---

## [INFORMATIONAL] No upper bound on `validTo` in `isValidSignature` creates unnecessarily long-lived CowSwap orders

**File:** `src/GPV2CompatibleAuction.sol:158-160`

**Description:**
The `validTo` check is:
```solidity
if (order.validTo < block.timestamp) {
    revert ExpiredOrder(order.validTo, block.timestamp);
}
```

There is no upper bound check like `order.validTo <= auctionStart + auctionDuration`. While the independent auction liveness check (line 150) prevents settlement after the auction ends, CowSwap maintains orders in its off-chain order book until `validTo`. Orders with far-future `validTo` remain in CowSwap's system long after the auction ends, creating noise for solvers who repeatedly attempt (and fail) to settle them.

Adding a check like `order.validTo <= auctionStart + auctionDuration + BUFFER` would keep the CowSwap order book cleaner.

**Impact:** Off-chain inefficiency for CowSwap solvers. No direct on-chain impact.

**Already known?** No. Informational only.

---

## Summary

| # | Severity | Title | File |
|---|----------|-------|------|
| 1 | Medium | Cross-auction stale CowSwap order settlement | GPV2CompatibleAuction.sol:148-160 |
| 2 | Medium | getAssetOutAmount reverts despite no-revert NatSpec | BaseAuction.sol:749-802 |
| 3 | Low | Uncapped multiplication overflow in checkUpkeep/bid | BaseAuction.sol:248,258,430 |
| 4 | Low | performUpkeep allows start+end in same call | BaseAuction.sol:305-370 |
| 5 | Low | _onAuctionEnd sweeps all assetOut indiscriminately | BaseAuction.sol:393-396 |
| 6 | Info | appData not validated in isValidSignature | GPV2CompatibleAuction.sol:119-176 |
| 7 | Info | No upper bound on validTo | GPV2CompatibleAuction.sol:158-160 |
