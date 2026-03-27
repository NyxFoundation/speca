# Fresh Audit Round 3 - Chainlink Payment Abstraction V2

**Auditor:** Fresh eyes, zero prior context
**Date:** 2026-03-27
**Scope:** Under-audited areas per specification

**Known findings skipped:** H-01, M-01, M-02, M-03, M-07, M-14, M-15

---

## Finding R3-01: `_getAssetOutAmount` Division by Zero When `assetOutUsdPrice` is Zero

**Severity:** Medium
**File:** `BaseAuction.sol`, lines 798-802
**Area:** `_getAssetOutAmount` Dutch auction math

### Description

The function `_getAssetOutAmount` fetches `assetOutUsdPrice` via `_getAssetPrice(s_assetOut, withValidation)`. When called with `withValidation = false` (from the external `getAssetOutAmount` view function, line 766), the price is fetched without validation. If the assetOut has no Data Streams price set (timestamp = 0, price = 0) and no data feed configured, or if both sources return zero, `assetOutUsdPrice` will be 0.

```solidity
return auctionUsdValue.mulDivUp(10 ** s_assetParams[s_assetOut].decimals, assetOutUsdPrice);
```

`mulDivUp` with a zero denominator will revert with a panic (division by zero). This causes the public `getAssetOutAmount()` view to revert unexpectedly instead of returning 0, which breaks integrator expectations for a function documented to "not revert but return zero instead."

When `withValidation = true` (called from `bid()` and `isValidSignature()`), `_getAssetPrice` will revert with `ZeroFeedData` first, which is the intended behavior. So the real impact is only on the view function path.

### Impact

External integrators or the `AuctionBidder.bid()` flow (which calls `getAssetOutAmount` at line 78 to compute the approval amount) could encounter unexpected reverts if the assetOut price oracle temporarily returns zero or is unconfigured. The `AuctionBidder.bid()` with empty solution array would fail with a panic instead of a descriptive error.

### Recommendation

Add a zero-price guard before the final division, returning 0 when `assetOutUsdPrice == 0` (consistent with the function's documented non-reverting behavior for the `withValidation = false` path).

---

## Finding R3-02: `_getAssetOutAmount` Returns Zero When `s_assetParams[s_assetOut].decimals` is 0

**Severity:** Low
**File:** `BaseAuction.sol`, line 802
**Area:** `_getAssetOutAmount` Dutch auction math

### Description

The expression `10 ** s_assetParams[s_assetOut].decimals` is used in the numerator. If `s_assetParams[s_assetOut]` has not been configured (decimals = 0), this evaluates to `10 ** 0 = 1`. This is not a revert, but it silently produces an incorrect (massively deflated) assetOut amount since the decimals normalization is wrong.

However, `performUpkeep` has the `whenAssetOutConfigured` modifier that checks `s_assetParams[s_assetOut].decimals != 0`, so auctions cannot start if assetOut params are missing. The `bid()` function does not have this check but relies on the auction having been started via `performUpkeep`.

The `getAssetOutAmount` external view has no such guard and could return silently incorrect values if queried before assetOut params are configured.

### Impact

Low. The view function could return misleading values to off-chain consumers if assetOut params are not yet configured, but live auctions require assetOut to be configured.

### Recommendation

Add a zero-check on `s_assetParams[s_assetOut].decimals` in `_getAssetOutAmount` or document that `getAssetOutAmount` results are only meaningful when assetOut params are set.

---

## Finding R3-03: `_setAssetOut` Deletes Old AssetOut Params But Does Not Handle Migration

**Severity:** Low
**File:** `BaseAuction.sol`, lines 500-516
**Area:** `_setAssetOut` configuration function

### Description

When `setAssetOut` changes the assetOut token, line 513 executes `delete s_assetParams[currentAssetOut]`. This removes the old assetOut's auction parameters entirely. However, if the old assetOut token is also an allowlisted auction asset (which is a valid use case -- the assetOut itself can be auctioned and forwarded to the receiver), its auction params are now gone.

After this change, the old assetOut token remains in `s_allowlistedAssets` with feed info intact, but its `AssetParams` are deleted. Any subsequent attempt to run `performUpkeep` with this asset would hit `AssetParamsNotSet` for the old assetOut (decimals == 0 check at line 334). But more subtly, `checkUpkeep` at line 234 would skip it silently since `assetParams.decimals == 0`.

### Impact

Low impact since this is an admin operation requiring `_whenNoLiveAuctions()` and is within the trusted admin trust boundary. However, the silent deletion of params for a token that might have been separately configured is unexpected and could lead to operational confusion.

### Recommendation

Document that changing assetOut will delete the old assetOut's params and require re-configuration if the old token should remain auctionable, or emit an event when params are deleted as a side-effect.

---

## Finding R3-04: `NativeTokenReceiver.receive()` Silently Swallows Failed Wrapping

**Severity:** Low / Informational
**File:** `NativeTokenReceiver.sol`, lines 48-55
**Area:** ETH handling

### Description

The `receive()` function uses a try/catch that silently catches any failure from `s_wrappedNativeToken.deposit()`:

```solidity
try s_wrappedNativeToken.deposit{value: msg.value}() {} catch {}
```

If the wrapped token contract's `deposit()` reverts (e.g., due to a bug, upgrade, or gas issues), the native ETH is accepted but **not** wrapped. It sits as raw ETH in the contract with no event emitted and no indication of failure. The `deposit()` external function (line 37) exists to wrap remaining balances, but there is no mechanism to alert operators that wrapping failed.

### Impact

ETH could accumulate unwrapped in the contract without operators knowing. The `deposit()` function serves as a manual recovery, but operational awareness requires monitoring contract ETH balance separately from WETH balance.

### Recommendation

Emit an event on wrapping failure in the catch block, or at minimum document this behavior for operators.

---

## Finding R3-05: `NativeTokenReceiver.deposit()` Wraps Entire Balance Including Amounts Not Yet Wrapped by `receive()`

**Severity:** Informational
**File:** `NativeTokenReceiver.sol`, lines 37-43
**Area:** ETH handling

### Description

The `deposit()` function wraps `address(this).balance` -- the entire native balance. This is expected behavior but worth noting: if the contract receives ETH through means other than the `receive()` function (e.g., via `selfdestruct`/`SELFDESTRUCT` from another contract, or via coinbase transactions), those funds will also be wrapped. This is actually desirable behavior for fund recovery.

No issue here -- including for completeness of audit.

---

## Finding R3-06: `_applyAssetParamsUpdates` Does Not Validate `startingPriceMultiplier > 0`

**Severity:** Low
**File:** `BaseAuction.sol`, lines 624-663
**Area:** `_applyAssetParamsUpdates` configuration

### Description

For non-assetOut assets, the validation checks:
1. `auctionDuration != 0` (line 647)
2. `endingPriceMultiplier >= i_minPriceMultiplier` (line 650)
3. `endingPriceMultiplier <= startingPriceMultiplier` (line 653)

However, `startingPriceMultiplier` itself is not checked for being zero or unreasonably small. If `startingPriceMultiplier == 0`, check #3 would require `endingPriceMultiplier <= 0`, which contradicts check #2 (since `i_minPriceMultiplier > 0` from constructor). So a zero startingPriceMultiplier is effectively prevented by transitivity.

But if `startingPriceMultiplier == endingPriceMultiplier` (both equal to `i_minPriceMultiplier`), the price is constant throughout the auction (no Dutch decay). This is valid behavior but may not be the intended use.

More critically, if `startingPriceMultiplier` is set to an extremely large value (e.g., `type(uint64).max`), the price multiplier starts very high and decays. In `_getAssetOutAmount`, the computation:

```solidity
uint256 priceMultiplier = assetInParams.startingPriceMultiplier
  - uint256(assetInParams.startingPriceMultiplier - assetInParams.endingPriceMultiplier)
    .mulDiv(elapsedTime, assetInParams.auctionDuration);
```

Since `startingPriceMultiplier` and `endingPriceMultiplier` are `uint64`, the difference fits in `uint64` (max ~1.8e19). `mulDiv` with `elapsedTime` (max = `auctionDuration`, which is `uint24`, max ~16.7M) and denominator `auctionDuration` will not overflow. So extreme values are arithmetically safe.

### Impact

Informational. No arithmetic overflow risk due to type constraints, and a zero `startingPriceMultiplier` is prevented by transitivity of existing checks.

---

## Finding R3-07: `_getAssetPrice` Data Feed Fallback Does Not Validate `answer > 0` Before `toUint256()`

**Severity:** Medium
**File:** `PriceManager.sol`, lines 386-401
**Area:** `_getAssetPrice` dual-oracle logic

### Description

When the Data Streams price is stale and the code falls back to the data feed:

```solidity
(, int256 answer,, uint256 dataFeedUpdatedAt,) = feedInfo.usdDataFeed.latestRoundData();

if (updatedAt < dataFeedUpdatedAt) {
    updatedAt = dataFeedUpdatedAt;
    price = answer.toUint256();  // <-- reverts if answer < 0
```

`SafeCast.toUint256(int256)` reverts if the input is negative. Chainlink data feeds can theoretically return negative values (particularly for certain asset types, though rare for USD price feeds). If a data feed returns a negative answer, the entire `_getAssetPrice` call reverts with a SafeCast overflow, rather than gracefully falling back to the stale Data Streams price or returning `isValid = false`.

This is distinct from M-03 (feed revert) because this is about the *answer value* being negative, not the feed call itself reverting.

When called with `withValidation = false` (e.g., from `checkUpkeep`), the intent is to get a best-effort price without reverting. A negative data feed answer would break this contract.

### Impact

A corrupted or unusual data feed returning a negative value would cause `_getAssetPrice` to revert even when `withValidation = false`, potentially blocking `checkUpkeep` and preventing auction lifecycle management.

### Recommendation

Check `answer > 0` before calling `toUint256()`. If answer is non-positive, skip the data feed fallback and stay with the (stale) Data Streams price.

---

## Finding R3-08: `_getAssetPrice` Data Feed Fallback Calls `decimals()` On Every Invocation

**Severity:** Informational (Gas)
**File:** `PriceManager.sol`, line 394
**Area:** `_getAssetPrice` dual-oracle logic

### Description

```solidity
uint8 decimals = feedInfo.usdDataFeed.decimals();
```

This is an external call made every time the data feed fallback path is hit. The decimals of a Chainlink data feed are immutable and never change. This call could be cached in `FeedInfo` to save gas.

### Impact

Minor gas waste. No security impact.

---

## Finding R3-09: `GPV2CompatibleAuction._onAuctionStart` Approves Based on Balance At Start Time

**Severity:** Medium
**File:** `GPV2CompatibleAuction.sol`, lines 86-93
**Area:** Approval lifecycle

### Description

```solidity
function _onAuctionStart(address asset) internal override {
    super._onAuctionStart(asset);
    IERC20(asset).forceApprove(i_gpV2VaultRelayer, IERC20(asset).balanceOf(address(this)));
}
```

The approval is set to the contract's balance of the asset *at the time the auction starts*. However, after the auction starts, additional tokens of the same asset could arrive at the contract (e.g., via direct transfer, or if the same token is the assetOut of another auction and gets sent here). This would mean tokens beyond the initial balance are NOT approved for the vault relayer.

More importantly, the `bid()` function in `BaseAuction` (the non-GPV2 path) transfers `amount` of the asset to `msg.sender` directly, reducing the balance below the approved amount. The CowSwap solver operating in parallel could try to fill an order for the full approved amount but the tokens have been transferred out by a direct bidder.

However, for the GPV2 path, `isValidSignature` checks `order.sellAmount <= assetInBalance` (line 144-146), so the CowSwap solver would get a revert on signature validation if balance is insufficient. The real edge case is:

1. Auction starts with 1000 tokens, approval set to 1000
2. A direct bidder buys 200 tokens via `bid()` -- balance is now 800
3. CowSwap solver tries to fill 900 tokens -- `isValidSignature` reverts due to insufficient balance check
4. This is correct behavior

But the converse is also interesting:
1. Auction starts with 1000 tokens, approval set to 1000
2. Someone sends 500 extra tokens to the contract directly
3. CowSwap solver tries to fill 1200 tokens
4. `isValidSignature` passes (balance = 1500 >= 1200)
5. But vault relayer's approval is only 1000, so the settlement would fail

The approval being capped at the start balance means extra tokens cannot be traded via CowSwap even if `isValidSignature` says they can.

### Impact

If extra tokens of the auctioned asset arrive after auction start, `isValidSignature` would validate orders up to the current balance, but the CowSwap vault relayer cannot actually transfer more than the approved amount. The CowSwap settlement transaction would revert despite signature validation passing.

This creates a discrepancy between what `isValidSignature` promises and what the vault relayer can execute. In practice, the solver would waste gas on a failing settlement.

### Recommendation

Either:
1. Set approval to `type(uint256).max` in `_onAuctionStart` (trust boundary: the vault relayer is already trusted as an immutable address), or
2. Add a balance cap check in `isValidSignature` that also considers the vault relayer's current allowance

---

## Finding R3-10: `Caller._call()` Allows Calling `address(0)` and Precompile Addresses

**Severity:** Low
**File:** `Caller.sol`, lines 21-44
**Area:** `_call()` edge cases

### Description

The `_call()` function does not validate the `target` address. A call to `address(0)` will succeed (returning empty bytes) on most EVM implementations -- `success` will be `true` with empty `response`. Similarly, calls to precompile addresses (1-9) with unexpected data may produce unexpected results.

The `_call` function is `internal` and only used by:
1. `_multiCall()` which is also internal
2. `AuctionBidder.auctionCallback()` which executes calls from the decoded `data` parameter

In `AuctionBidder.auctionCallback()`, the `calls` array is provided by the AUCTION_BIDDER_ROLE holder (semi-trusted). A call to `address(0)` would succeed silently but have no effect. This is likely harmless but unexpected.

### Impact

Low. The semi-trusted AUCTION_BIDDER_ROLE could include no-op calls to `address(0)` in their solution, but this causes no harm -- just wasted gas.

### Recommendation

Consider adding `target != address(0)` validation in `_call()`, or document that zero-address calls are no-ops.

---

## Finding R3-11: `Caller._call()` Sends No Value But Target Receives `msg.value` If Contract Has Balance

**Severity:** Informational
**File:** `Caller.sol`, line 27
**Area:** `_call()` edge cases

### Description

```solidity
(bool success, bytes memory response) = target.call(data);
```

The call sends no explicit value (`value: 0` is implicit). This is correct -- ETH is not forwarded. Including for completeness since the `NativeTokenReceiver` contract can hold ETH, but `_call` in the Caller abstract contract does not forward any of it. This is the expected and safe behavior.

No issue.

---

## Finding R3-12: `_applyAssetParamsUpdates` Allows Re-adding the Same Asset Params Without Change

**Severity:** Informational
**File:** `BaseAuction.sol`, lines 624-663
**Area:** `_applyAssetParamsUpdates` configuration

### Description

Unlike `_setMinBidUsdValue`, `_setAssetOut`, `_setAssetOutReceiver`, and `_setFeeAggregator` which all have `ValueNotUpdated` checks, `_applyAssetParamsUpdates` does not check if the new params are identical to the existing ones. An admin can call it with the same params and it will emit `AssetParamsUpdated` events without actual changes.

### Impact

Informational. No security impact. Could confuse off-chain monitoring.

---

## Finding R3-13: `_onFeedInfoUpdate` in BaseAuction Blocks Feed Changes During Unrelated Live Auctions

**Severity:** Low
**File:** `BaseAuction.sol`, lines 688-697
**Area:** `_onFeedInfoUpdate` configuration

### Description

```solidity
function _onFeedInfoUpdate(address asset, bool isRemoved) internal override {
    if ((asset == s_assetOut && _liveAuctionExists()) || s_auctionStarts[asset] != 0) {
        revert LiveAuction();
    }
}
```

When updating feed info for the assetOut, it reverts if *any* live auction exists (via `_liveAuctionExists()`). This means updating the assetOut's feed info is blocked even if the live auctions are for completely unrelated assets.

This is a design choice for safety (assetOut price affects all auctions), but it means feed info updates to the assetOut are blocked by any ongoing auction, which could span indefinitely if auctions are continuously active. Admin would need to end all auctions first.

### Impact

Low operational impact. This is a conservative safety measure but could delay critical feed updates in emergencies. The admin can pause the contract as a workaround, but `applyFeedInfoUpdates` requires `ASSET_ADMIN_ROLE`, not the pause mechanism.

---

## Finding R3-14: `checkUpkeep` Uses `assetPrice` That May Be Zero/Invalid For USD Value Calculation

**Severity:** Low
**File:** `BaseAuction.sol`, lines 247-254
**Area:** Auction lifecycle

### Description

In `checkUpkeep`, for assets with live auctions, the code computes:

```solidity
uint256 assetBalanceUsdValue = (assetBalance * assetPrice) / (10 ** assetParams.decimals);
```

Where `assetPrice` comes from `_getAssetPrice(asset, false)` which may return 0 if the price is stale/zero. If `assetPrice == 0`, then `assetBalanceUsdValue == 0`, which is always less than `minAuctionSizeUsd`, so the auction would be flagged for ending.

However, this is gated by `isPriceValid`:
```solidity
|| (isPriceValid && assetBalanceUsdValue < assetParams.minAuctionSizeUsd)
```

When `isPriceValid == false` (stale/zero price), the dust check is skipped, and the auction is only ended if the duration has elapsed. This is correct behavior -- it avoids ending auctions based on invalid price data.

No issue upon closer inspection.

---

## Finding R3-15: `GPV2CompatibleAuction._onAuctionEnd` Revokes Approval But Does Not Check for Pending Settlements

**Severity:** Informational
**File:** `GPV2CompatibleAuction.sol`, lines 96-104
**Area:** Approval lifecycle

### Description

When an auction ends:
```solidity
function _onAuctionEnd(address asset, bool hasFeeAggregator) internal override {
    super._onAuctionEnd(asset, hasFeeAggregator);
    IERC20(asset).forceApprove(i_gpV2VaultRelayer, 0);
}
```

The approval is revoked immediately. If a CowSwap batch settlement is in-flight at the same moment (the `performUpkeep` ending the auction and the CowSwap settlement are both pending in the mempool), the settlement could fail because the approval was just revoked.

This is a race condition between `performUpkeep` (ending the auction) and CowSwap settlement execution. The ORDER_MANAGER_ROLE can use `invalidateOrders()` to cancel orders before ending auctions, but there is no enforced ordering.

### Impact

Informational. In practice, CowSwap settlements and upkeep calls are not typically in the same block, and the ORDER_MANAGER can preemptively invalidate orders. However, a MEV bot could theoretically sandwich: observe a pending settlement, front-run with `performUpkeep` to end the auction, causing the settlement to fail.

This requires AUCTION_WORKER_ROLE to submit the `performUpkeep`, which is trusted, so MEV from external actors is not directly possible.

---

## Finding R3-16: `_getAssetPrice` Comparison Logic May Return Stale Data Streams Price Over Fresher Data Feed

**Severity:** Medium
**File:** `PriceManager.sol`, lines 380-401
**Area:** `_getAssetPrice` dual-oracle logic

### Description

The fallback logic is:

```solidity
// Prioritize Data Streams price.
price = priceInfo.usdPrice;       // Data Streams price
updatedAt = priceInfo.timestamp;  // Data Streams timestamp

// If the Data Streams price is stale, fetch the Data Feed price
if (updatedAt < minTimestamp && feedInfo.usdDataFeed != AggregatorV3Interface(address(0))) {
    (, int256 answer,, uint256 dataFeedUpdatedAt,) = feedInfo.usdDataFeed.latestRoundData();

    // Use the most recent timestamp
    if (updatedAt < dataFeedUpdatedAt) {
        updatedAt = dataFeedUpdatedAt;
        price = answer.toUint256();
        // ... scale decimals
    }
}
```

The issue: if Data Streams price timestamp is 0 (never set, e.g., new asset with only a data feed configured), then `priceInfo.usdPrice = 0` and `priceInfo.timestamp = 0`. The condition `updatedAt < minTimestamp` is true (0 < minTimestamp), so we enter the fallback. Then `updatedAt < dataFeedUpdatedAt` is true (0 < any timestamp), so we use the data feed price. This works correctly.

However, consider: Data Streams reports a price at T=100, then the Data Streams feed becomes stale (threshold = 60, current time = 200). We fetch the data feed, which was last updated at T=90. The check `updatedAt < dataFeedUpdatedAt` is `100 < 90` which is FALSE. So we keep the Data Streams price from T=100 even though it is stale.

Both prices are stale in this case, but the code keeps the fresher one (T=100 > T=90), which is actually correct -- it picks the most recent data point. The `isValid` flag will correctly be `false` since both are stale.

But what if Data Streams was at T=100 with price=50 and the data feed is at T=90 with price=100? We keep the stale Data Streams price even though the data feed is only slightly older. The `isValid = false` flag is correct, but when `withValidation = false` (e.g., `checkUpkeep`), the returned price is used for USD value calculations. Using a price from T=100 vs T=90 is marginal, and picking the fresher one is reasonable.

Upon deeper reflection, this is working as intended -- the code explicitly documents "Use the most recent timestamp between the Data Streams price and the Data Feed price."

**Withdrawn** -- not a real finding. The logic is sound.

---

## Finding R3-17: `_applyFeedInfoUpdates` Feed ID Rotation Does Not Delete Old Asset's `s_feedInfo.dataStreamsFeedId`

**Severity:** Informational
**File:** `PriceManager.sol`, lines 264-278
**Area:** `_applyFeedInfoUpdates` (PriceManager)

### Description

When a Data Streams feed ID is being "rotated" from one asset to another (lines 265-278), the code correctly:
1. Checks the previous asset still has a data feed as backup (line 271)
2. Clears the previous asset's `dataStreamsFeedId` to `bytes32(0)` (line 275)
3. Clears the previous asset's `dataStreamsFeedDecimals` to 0 (line 276)
4. Deletes the previous asset's Data Streams price (line 277)

But then at line 280:
```solidity
if (previousAssetForFeedId != asset) s_dataStreamsFeedIdToAsset[feedInfo.dataStreamsFeedId] = asset;
```

And at line 283-299, the new feed info is written for the current asset. This all works correctly.

However, the old asset's `s_feedInfo` still has `usdDataFeed`, `stalenessThreshold` intact (only `dataStreamsFeedId` and `dataStreamsFeedDecimals` were zeroed). This is correct since the old asset now relies solely on the data feed.

No issue upon thorough review.

---

## Finding R3-18: `performUpkeep` Uses `eligibleAssets[i].amount` From Untrusted Input for USD Value Check

**Severity:** Low
**File:** `BaseAuction.sol`, lines 324-348
**Area:** Auction lifecycle

### Description

```solidity
uint256 availableAssetUsdValue = (eligibleAssets[i].amount * assetPrice) / (10 ** assetDecimals);
if (availableAssetUsdValue < assetParams.minAuctionSizeUsd) {
    revert AmountBelowMinAuctionSize(availableAssetUsdValue, assetParams.minAuctionSizeUsd);
}
```

The `eligibleAssets[i].amount` comes from the `performData` parameter, which is provided by the AUCTION_WORKER_ROLE caller. This value was originally computed in `checkUpkeep` as the fee aggregator balance, but `performUpkeep` does not re-verify it against the actual transferred amount.

Before this check, `s_feeAggregator.transferForSwap(address(this), eligibleAssets)` (line 321) transfers the specified amounts. If the fee aggregator has less balance than specified, the transfer will revert (SafeERC20). So `amount` is bounded by what the fee aggregator actually has.

However, the AUCTION_WORKER_ROLE could pass a smaller `amount` than what the fee aggregator holds, causing the USD value check to pass with a lower threshold. This would start an auction with less funds. But the actual funds transferred match the `amount`, so the auction balance is consistent.

The AUCTION_WORKER_ROLE could also pass `amount = 0`, but then `transferForSwap` would revert due to the zero amount check in `_transferAsset`.

No exploitable issue found, but the trust assumption on AUCTION_WORKER_ROLE is important to note.

---

## Finding R3-19: `_getAssetOutAmount` `mulWadUp` Could Cause Slight Overpayment by Bidders

**Severity:** Informational
**File:** `BaseAuction.sol`, line 799
**Area:** `_getAssetOutAmount` Dutch auction math

### Description

The computation uses rounding-up functions (`mulDivUp`, `mulWadUp`) throughout:

```solidity
uint256 auctionUsdValue = amountIn.mulDivUp(assetInUsdPrice, 10 ** assetInParams.decimals).mulWadUp(priceMultiplier);
return auctionUsdValue.mulDivUp(10 ** s_assetParams[s_assetOut].decimals, assetOutUsdPrice);
```

All three operations round up. This means the bidder pays slightly more assetOut than the theoretical exact value. This is by design -- it protects the protocol against rounding in the bidder's favor. However, with three consecutive round-ups, the cumulative rounding error could be up to 3 wei above the true value in the worst case.

### Impact

Informational. Rounding in the protocol's favor is the correct approach. The maximum rounding error is negligible (a few wei).

---

## Summary Table

| ID | Severity | Area | Title |
|---|---|---|---|
| R3-01 | Medium | `_getAssetOutAmount` | Division by zero when `assetOutUsdPrice` is 0 (view function path) |
| R3-02 | Low | `_getAssetOutAmount` | Silent miscalculation when assetOut params not configured |
| R3-03 | Low | `_setAssetOut` | Deletes old assetOut params as side effect |
| R3-04 | Low | `NativeTokenReceiver` | Silent swallow of failed wrapping in receive() |
| R3-06 | Informational | `_applyAssetParamsUpdates` | No explicit validation of startingPriceMultiplier > 0 (prevented by transitivity) |
| R3-07 | Medium | `_getAssetPrice` | Data feed negative answer causes revert via SafeCast even without validation |
| R3-09 | Medium | `_onAuctionStart` (GPV2) | Approval amount capped at start-time balance creates inconsistency with isValidSignature |
| R3-10 | Low | `Caller._call()` | No validation of target address (address(0) succeeds silently) |
| R3-12 | Informational | `_applyAssetParamsUpdates` | No duplicate-value check allows no-op updates |
| R3-13 | Low | `_onFeedInfoUpdate` | AssetOut feed updates blocked by unrelated live auctions |
| R3-15 | Informational | `_onAuctionEnd` (GPV2) | Race condition between approval revocation and in-flight settlements |
| R3-19 | Informational | `_getAssetOutAmount` | Triple round-up causes minor overpayment (by design) |
