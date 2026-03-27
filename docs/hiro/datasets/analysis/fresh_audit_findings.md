# Fresh Security Audit Findings -- Chainlink Auction System

**Auditor:** Fresh auditor (no prior codebase knowledge)
**Date:** 2026-03-26
**Scope:** All Solidity files in `src/` and subdirectories
**Trust Model:** DEFAULT_ADMIN_ROLE, AUCTION_WORKER_ROLE, PRICE_ADMIN_ROLE, ASSET_ADMIN_ROLE, ORDER_MANAGER_ROLE are trusted. AUCTION_BIDDER_ROLE is semi-trusted. CowSwap Solver and `bid()` callers are untrusted.

---

## [H-01] CowSwap Solver Can Steal Auction Funds via Stale `isValidSignature` -- Time-of-Check-Time-of-Use (TOCTOU) Between Validation and Settlement

**File:** `src/GPV2CompatibleAuction.sol`, lines 119-176
**File:** `src/BaseAuction.sol`, lines 410-458

**Severity:** High

**Description:**
`isValidSignature()` is a `view` function that validates a CowSwap order at the moment it is called. However, there is a critical TOCTOU gap: the CowSwap settlement contract calls `isValidSignature()` to validate, then later executes the token transfers. Between validation and execution, the auction state can change:

1. The auction price is computed at `isValidSignature()` call time (line 148-154), but the actual settlement can happen in a later transaction within the same block or a subsequent block.
2. The `elapsedTime` is checked against `block.timestamp` (line 148), but if the settlement is batched with other transactions in CowSwap, the solver controls the order of settlement within a batch.

More critically, `isValidSignature()` checks `order.sellAmount > assetInBalance` (line 145) against the contract's current balance. But CowSwap settlement supports **partial fills** (line 168 enforces `partiallyFillable = true`). The solver can create a single order for the entire auction balance, get it validated, then the CowSwap settlement contract can fill it in multiple partial settlements. Between partial fills, the `bid()` function from `BaseAuction` could also be called (since `bid()` is fully permissionless), reducing the contract's balance. However, the CowSwap vault relayer still has the full approval from `_onAuctionStart` (line 92), meaning it can drain more tokens than intended if the balance was topped up (e.g., by direct transfer or another auction starting).

**Impact:** A malicious solver could potentially extract more value from the auction than the pricing curve intended by exploiting the gap between validation and settlement timing.

**Line References:**
- `GPV2CompatibleAuction.sol:92` -- approval set to full balance at auction start
- `GPV2CompatibleAuction.sol:119-176` -- view-time validation
- `GPV2CompatibleAuction.sol:148` -- elapsedTime computed from block.timestamp
- `GPV2CompatibleAuction.sol:154` -- minBuyAmount computed from current time

---

## [H-02] Approval Set to Balance-at-Start-Time Only -- CowSwap Orders Cannot Cover Full Auction Amount if Tokens Are Sent Directly

**File:** `src/GPV2CompatibleAuction.sol`, line 92

**Severity:** Medium

**Description:**
In `_onAuctionStart`, the vault relayer approval is set to `IERC20(asset).balanceOf(address(this))` -- the balance at auction start time. If additional tokens of the same asset are transferred directly to the contract after the auction starts (e.g., by accident, or from another source), the CowSwap vault relayer cannot access those extra tokens even though `isValidSignature` would validate against the current balance (line 144). This creates an inconsistency between what `isValidSignature` validates and what the vault relayer can actually transfer.

Conversely, this is actually a safety property for the `bid()` path -- but it creates an exploitable state inconsistency for the CowSwap path.

**Line References:**
- `GPV2CompatibleAuction.sol:92` -- `forceApprove(i_gpV2VaultRelayer, IERC20(asset).balanceOf(address(this)))`
- `GPV2CompatibleAuction.sol:144` -- `uint256 assetInBalance = order.sellToken.balanceOf(address(this))`

---

## [H-03] `bid()` Callback Enables Arbitrary Code Execution by Any Address -- Flash-Loan Style Attack Vector

**File:** `src/BaseAuction.sol`, lines 410-458

**Severity:** High

**Description:**
The `bid()` function (line 414) is callable by anyone (`whenNotPaused`, no role restriction). It follows a pattern where:
1. It transfers `amount` of auction tokens to `msg.sender` (line 444)
2. If `data.length != 0`, it calls `IAuctionCallback(msg.sender).auctionCallback(...)` (line 449)
3. It then pulls `assetOutAmount` of `assetOut` tokens from `msg.sender` via `safeTransferFrom` (line 453)

This is essentially a flash-loan pattern. The bidder receives tokens first, executes arbitrary logic in the callback, and then must return `assetOut` tokens. While there is a reentrancy guard (`s_entered`, lines 415-418, 457), the callback gives the bidder a powerful primitive:

- The bidder receives the auction tokens **before** paying. They can use these tokens in DeFi protocols (swap, provide liquidity, etc.) within the callback.
- A bidder could manipulate the price oracle in their callback (if the oracle is manipulable) to get a better price on a subsequent bid, though the reentrancy guard prevents immediate re-entry.

While this flash-loan pattern is likely intentional for the `AuctionBidder` contract, the fact that it's available to any address (not just AUCTION_BIDDER_ROLE holders) means any external contract can exploit this.

**Impact:** Any address can perform flash-loan-like operations using auction assets. This is a powerful primitive that could be chained with oracle manipulation or other DeFi interactions.

**Line References:**
- `BaseAuction.sol:414` -- `external whenNotPaused` (no role check)
- `BaseAuction.sol:444` -- tokens sent to caller first
- `BaseAuction.sol:449` -- callback invoked on caller
- `BaseAuction.sol:453` -- payment pulled after

---

## [H-04] `AuctionBidder.auctionCallback` Executes Arbitrary External Calls via `_multiCall` -- AUCTION_BIDDER_ROLE Can Call Any Contract

**File:** `src/AuctionBidder.sol`, lines 97-112
**File:** `src/Caller.sol`, lines 21-44

**Severity:** High (given AUCTION_BIDDER_ROLE is in scope)

**Description:**
The `auctionCallback` function (line 97) receives `data`, decodes it into `Call[]` structs (line 107), and executes them via `_multiCall` (line 109). Each `Call` struct contains an arbitrary `target` and arbitrary `data` (Caller.sol, lines 12-15). There is **no validation** on what targets or selectors can be called.

A semi-trusted `AUCTION_BIDDER_ROLE` holder can:
1. Call `bid()` on the auction with crafted `solution` data
2. The callback executes arbitrary calls to any contract with any calldata
3. This effectively gives AUCTION_BIDDER_ROLE the ability to do anything the AuctionBidder contract can do, including:
   - Calling `approve()` on any token the AuctionBidder holds, granting allowance to an attacker address
   - Interacting with any DeFi protocol
   - Calling the auction contract itself (though reentrancy guard would block `bid()`)

The only check is `msg.sender != address(s_auction) || from != address(this)` (line 103), which verifies the callback comes from the auction and was initiated by this contract. But the arbitrary call execution within the callback is unconstrained.

**Impact:** AUCTION_BIDDER_ROLE (semi-trusted) gains unrestricted arbitrary external call capability through the AuctionBidder contract. This effectively escalates to full control over any assets held by or approved to the AuctionBidder.

**Line References:**
- `AuctionBidder.sol:107` -- `abi.decode(data, (Call[]))`
- `AuctionBidder.sol:109` -- `_multiCall(calls)` with no target/selector restrictions
- `Caller.sol:27` -- raw `target.call(data)` with no validation
- `AuctionBidder.sol:69` -- `AUCTION_BIDDER_ROLE` triggers the flow

---

## [M-01] `isValidSignature` Uses `block.timestamp` for Price While CowSwap Settlement May Execute at Different Time

**File:** `src/GPV2CompatibleAuction.sol`, lines 148-156

**Severity:** Medium

**Description:**
The `isValidSignature` function computes `elapsedTime = block.timestamp - auctionStart` (line 148) and uses this to calculate `minBuyAmount` via `_getAssetOutAmount` (line 154). The price multiplier decays linearly over time in `_getAssetOutAmount` (BaseAuction.sol, line 793-795).

In CowSwap's architecture, the solver calls `isValidSignature` during settlement. However, the validation happens at the time of the `settle()` transaction. If a solver submits a batch at time T where the price is favorable, but the transaction gets included at time T+N (due to network congestion, MEV, etc.), the price will be validated at T+N's block.timestamp. This means:

- The solver sees a price at T and constructs an order
- The validation happens at T+N where the auction price has decayed further (become cheaper for the buyer)
- The `minBuyAmount` check at line 155 passes because the actual settlement time gives a lower price than expected

This benefits the solver at the expense of the protocol, as the solver gets a better price than what was visible when they constructed the order.

**Line References:**
- `GPV2CompatibleAuction.sol:148` -- `uint256 elapsedTime = block.timestamp - auctionStart`
- `GPV2CompatibleAuction.sol:154` -- `_getAssetOutAmount(assetParams, sellTokenUsdPrice, order.sellAmount, elapsedTime, true)`
- `BaseAuction.sol:793-795` -- linear price decay computation

---

## [M-02] No Minimum `buyAmount` Validation Relative to `sellAmount` in `isValidSignature` -- Solver Can Underpay After Auction Duration Edge

**File:** `src/GPV2CompatibleAuction.sol`, lines 148-156

**Severity:** Medium

**Description:**
The `isValidSignature` function checks `elapsedTime > assetParams.auctionDuration` and reverts with `InvalidAuction` if so (line 150-152). However, right at `elapsedTime == assetParams.auctionDuration`, the price multiplier is at its minimum (`endingPriceMultiplier`). If the `endingPriceMultiplier` is set to a value like `0.8e18` (20% discount), the solver can buy at maximum discount.

The issue is that in `_getAssetOutAmount` (BaseAuction.sol, line 785), `elapsedTime` is bounded: `elapsedTime = elapsedTime > assetInParams.auctionDuration ? assetInParams.auctionDuration : elapsedTime`. But in `isValidSignature`, the check at line 150 already reverts if `elapsedTime > auctionDuration`. So at exactly `elapsedTime == auctionDuration`, the multiplier is at the minimum.

Meanwhile, in `bid()` (BaseAuction.sol, line 425), the check is `auctionStart == 0 || elapsedTime > assetParams.auctionDuration`, which also allows bidding at exactly `elapsedTime == auctionDuration`. This is consistent, but worth noting that both paths allow trading at the maximum discount point.

**Line References:**
- `GPV2CompatibleAuction.sol:150-152` -- `if (elapsedTime > assetParams.auctionDuration)`
- `BaseAuction.sol:425` -- `if (auctionStart == 0 || elapsedTime > assetParams.auctionDuration)`
- `BaseAuction.sol:785` -- elapsedTime bounded to auctionDuration

---

## [M-03] `bid()` Does Not Verify `asset != s_assetOut` -- Bidder Can Bid on AssetOut if it Has an Active Auction Start

**File:** `src/BaseAuction.sol`, lines 410-458

**Severity:** Medium

**Description:**
The `bid()` function checks `s_auctionStarts[asset] != 0` (line 421-425) but does not check whether `asset == s_assetOut`. In `performUpkeep` (line 350-351), when `asset == s_assetOut`, the contract transfers the balance to `s_assetOutReceiver` instead of starting an auction. So `s_auctionStarts[s_assetOut]` should never be non-zero in normal operation.

However, if a race condition or admin misconfiguration causes `s_auctionStarts[s_assetOut]` to be set (e.g., through a code upgrade path or if `setAssetOut` is called after an auction starts for an asset that then becomes the new `assetOut`), a bidder could bid on the `assetOut` itself. The `_getAssetOutAmount` function would then compute the output amount using the same asset for both input and output pricing, which could lead to unexpected behavior.

Note: `_setAssetOut` has `_whenNoLiveAuctions()` guard (line 503), making this scenario unlikely in practice. But the defense-in-depth check is missing from `bid()`.

**Line References:**
- `BaseAuction.sol:414-425` -- bid() does not check asset != s_assetOut
- `BaseAuction.sol:350-351` -- performUpkeep handles assetOut specially
- `BaseAuction.sol:503` -- _setAssetOut has _whenNoLiveAuctions guard

---

## [M-04] Dual Settlement Path (CowSwap + Direct Bid) Creates Race Condition on Auction Balance

**File:** `src/GPV2CompatibleAuction.sol`, lines 86-103
**File:** `src/BaseAuction.sol`, lines 410-458

**Severity:** Medium

**Description:**
`GPV2CompatibleAuction` inherits both the CowSwap `isValidSignature` path and the direct `bid()` path from `BaseAuction`. Both paths compete for the same auction token balance:

1. CowSwap path: The vault relayer has an approval (line 92) and can transfer tokens based on validated orders
2. Direct bid path: `bid()` transfers tokens via `safeTransfer` (line 444)

If both paths are used simultaneously:
- A CowSwap order is validated via `isValidSignature` checking the current balance
- Before the CowSwap settlement executes, someone calls `bid()` and removes tokens
- The CowSwap settlement then fails because the balance is insufficient, but the vault relayer's approval was already set

More concerning: if `bid()` reduces the balance, the approval from line 92 still remains at the original balance. If tokens are later sent to the contract (e.g., during a new auction), the stale approval could be exploited.

However, `_onAuctionEnd` (line 96-103) revokes the approval, mitigating stale approval risk between auctions. The main risk is within a single auction lifetime.

**Line References:**
- `GPV2CompatibleAuction.sol:92` -- approval set at auction start
- `GPV2CompatibleAuction.sol:103` -- approval revoked at auction end
- `BaseAuction.sol:437-439` -- bid checks available balance
- `BaseAuction.sol:444` -- bid transfers tokens out

---

## [M-05] `checkUpkeep` Calculates `assetBalanceUsdValue` Without Price Validation -- Can End Auctions Based on Invalid Prices

**File:** `src/BaseAuction.sol`, lines 238-253

**Severity:** Medium

**Description:**
In `checkUpkeep`, the asset price is fetched without validation (line 238: `_getAssetPrice(asset, false)`). This price is then used to compute `assetBalanceUsdValue` (line 248) to determine if an auction should end early (line 249-253).

If the price is stale or zero (invalid), the `isPriceValid` flag is checked for the early-end condition at line 251: `isPriceValid && assetBalanceUsdValue < assetParams.minAuctionSizeUsd`. So if the price is invalid, the early-end due to dust won't trigger. However, if the price returned is non-zero but stale (edge case where `isValid` is false but price is non-zero), the `assetBalanceUsdValue` computation at line 248 would still proceed using the stale price for the duration-based end check at line 250.

The duration-based end check (`auctionStart + assetParams.auctionDuration < block.timestamp`) is independent of price and is fine. But the view function returns `performData` that could lead `performUpkeep` to end an auction that shouldn't be ended (or not end one that should be).

Since `checkUpkeep` is a view function and `performUpkeep` is called by trusted AUCTION_WORKER_ROLE, the impact is limited.

**Line References:**
- `BaseAuction.sol:238` -- `_getAssetPrice(asset, false)` without validation
- `BaseAuction.sol:248` -- `assetBalanceUsdValue = (assetBalance * assetPrice) / (10 ** assetParams.decimals)`
- `BaseAuction.sol:250-253` -- end condition uses both duration and value check

---

## [M-06] Precision Loss in `_getAssetOutAmount` Due to Intermediate Rounding with Different Decimal Tokens

**File:** `src/BaseAuction.sol`, lines 777-803

**Severity:** Medium

**Description:**
The `_getAssetOutAmount` function performs multiple chained multiplications and divisions:

```
priceMultiplier = startingPriceMultiplier - (startingPriceMultiplier - endingPriceMultiplier).mulDiv(elapsedTime, auctionDuration)  // line 793-795
auctionUsdValue = amountIn.mulDivUp(assetInUsdPrice, 10 ** assetInParams.decimals).mulWadUp(priceMultiplier)  // line 799
assetOutAmount = auctionUsdValue.mulDivUp(10 ** s_assetParams[s_assetOut].decimals, assetOutUsdPrice)  // line 802
```

When `assetOut` is USDC (6 decimals) and `assetIn` is WETH (18 decimals):
- `amountIn` is in 18 decimals
- `assetInUsdPrice` is in 18 decimals
- First `mulDivUp`: `amountIn * assetInUsdPrice / 10^18` -- this gives USD value in 18 decimals (correct)
- `mulWadUp(priceMultiplier)`: multiplies by multiplier and divides by 1e18 -- gives discounted USD value in 18 decimals
- Second `mulDivUp`: `auctionUsdValue * 10^6 / assetOutUsdPrice` -- converts to USDC amount

The issue is that intermediate rounding from `mulDivUp` compounds. Each `mulDivUp` rounds up by at most 1 unit. With USDC (6 decimals), the final rounding up by 1 unit of USDC is `0.000001 USDC`, which is negligible. But with very small bid amounts or very high price ratios, the cumulative rounding could become a larger percentage of the bid.

More importantly, the `mulDiv` on line 795 for `priceMultiplier` rounds **down**, which means the multiplier is slightly lower than the true value, resulting in a slightly lower price for the buyer. This benefits the buyer (not the protocol) by a tiny amount on each trade.

With `startingPriceMultiplier = 1.1e18`, `endingPriceMultiplier = 0.98e18`, and `auctionDuration = 3600`, the decay per second is `0.12e18 / 3600 = 33333333333333.33...` which truncates to `33333333333333`. Over 3600 seconds this gives `0.119999999999988e18` instead of `0.12e18`, meaning the ending price is `0.980000000000012e18` instead of `0.98e18` -- a negligible difference but consistently in the buyer's favor.

**Line References:**
- `BaseAuction.sol:793-795` -- priceMultiplier computation with mulDiv (rounds down)
- `BaseAuction.sol:799` -- auctionUsdValue with mulDivUp
- `BaseAuction.sol:802` -- final conversion with mulDivUp

---

## [M-07] `isValidSignature` Does Not Check `s_minBidUsdValue` -- CowSwap Orders Can Be Arbitrarily Small

**File:** `src/GPV2CompatibleAuction.sol`, lines 119-176
**File:** `src/BaseAuction.sol`, lines 431-435

**Severity:** Medium

**Description:**
The direct `bid()` function enforces a minimum bid USD value check (BaseAuction.sol, lines 431-435):
```solidity
if (bidUsdValue < minBidUsdValue) {
    revert BidValueTooLow(bidUsdValue, minBidUsdValue);
}
```

However, `isValidSignature` in `GPV2CompatibleAuction.sol` does **not** perform this same check. A CowSwap solver can create orders with arbitrarily small `sellAmount` values (as long as `sellAmount > 0`, checked at line 141). This bypasses the minimum bid size protection.

This could be exploited for:
1. **Dust attacks**: Creating many small orders that each cost gas to settle but extract tiny amounts from the auction
2. **Price probing**: Testing the exact price boundary with minimal capital at risk
3. **Griefing**: Filling the CowSwap order book with many small orders, consuming gas and settlement capacity

**Line References:**
- `GPV2CompatibleAuction.sol:141` -- only checks `order.sellAmount == 0`
- `BaseAuction.sol:431-435` -- `bid()` enforces `s_minBidUsdValue` check
- No equivalent check in `isValidSignature`

---

## [M-08] `_onAuctionStart` Approval Race Condition with `forceApprove`

**File:** `src/GPV2CompatibleAuction.sol`, lines 86-93

**Severity:** Low

**Description:**
`_onAuctionStart` calls `forceApprove` to set the vault relayer's allowance to the current balance. Using `forceApprove` from SafeERC20 is safe against the ERC20 approve race condition. However, if `_onAuctionStart` is called and then tokens are sent to the contract before any CowSwap settlement, those extra tokens have no approval coverage.

This is more of a design note than a vulnerability -- the approval is a snapshot of the balance at start time.

**Line References:**
- `GPV2CompatibleAuction.sol:92`

---

## [L-01] `bid()` Arithmetic Can Underflow if `auctionStart` is in the Future

**File:** `src/BaseAuction.sol`, line 423

**Severity:** Low

**Description:**
The line `uint256 elapsedTime = block.timestamp - auctionStart` (line 423) will underflow if `auctionStart > block.timestamp`. Since Solidity 0.8.26 has overflow/underflow protection, this would revert. The `auctionStart` is set to `block.timestamp` in `performUpkeep` (line 353), so `auctionStart` should always be <= `block.timestamp`. However, if there's ever a way to set `auctionStart` to a future timestamp, bids would be bricked until that timestamp.

This is defensive -- currently safe but fragile.

**Line References:**
- `BaseAuction.sol:423` -- `uint256 elapsedTime = block.timestamp - auctionStart`
- `BaseAuction.sol:353` -- `s_auctionStarts[asset] = block.timestamp`

---

## [L-02] `isValidSignature` Does Not Validate `order.appData`

**File:** `src/GPV2CompatibleAuction.sol`, lines 119-176

**Severity:** Low

**Description:**
The `isValidSignature` function validates many order fields but does not check `order.appData`. The `appData` field is a `bytes32` that can contain arbitrary data in CowSwap. While this is not directly exploitable, it means any appData value will be accepted, which could be relevant for off-chain monitoring or metadata expectations.

**Line References:**
- `GPV2CompatibleAuction.sol:119-176` -- no check on `order.appData`

---

## [L-03] `AuctionBidder.bid()` Does Not Check `amount > 0`

**File:** `src/AuctionBidder.sol`, lines 65-92

**Severity:** Low

**Description:**
The `AuctionBidder.bid()` function does not validate that `amount > 0` before calling `auction.bid()`. While `BaseAuction.bid()` would revert due to `bidUsdValue < minBidUsdValue` check (since 0 * price = 0), this wastes gas and the error message would be confusing (`BidValueTooLow` instead of a clear "zero amount" error).

**Line References:**
- `AuctionBidder.sol:65-81` -- no `amount > 0` check

---

## [L-04] `getAssetOutAmount` View Function Can Return Different Value Than `bid()` Actually Charges

**File:** `src/BaseAuction.sol`, lines 749-767 vs. lines 410-458

**Severity:** Low

**Description:**
The `getAssetOutAmount` view function (line 749) and the actual `bid()` function (line 410) can return different amounts for the same parameters because:

1. `getAssetOutAmount` caps `amount` to `availableBalance` (line 762): `amount = amount > availableBalance ? availableBalance : amount`
2. `getAssetOutAmount` uses `_getAssetPrice(assetIn, false)` (no validation, line 764)
3. `bid()` uses `_getAssetPrice(asset, true)` (with validation, line 429)

If a user calls `getAssetOutAmount` to preview the price, then calls `bid()`, they might get a different amount if:
- The balance changed between calls
- The price feed state changed between calls

Additionally, `getAssetOutAmount` accepts an arbitrary `timestamp` parameter (line 752), while `bid()` always uses `block.timestamp` (line 423). A user previewing with a future timestamp would get a different (lower) price than what they'd actually pay.

**Line References:**
- `BaseAuction.sol:762` -- amount capping in view
- `BaseAuction.sol:764` -- no price validation in view
- `BaseAuction.sol:429` -- price validation in bid

---

## [L-05] `AuctionBidder.bid()` Silently Does Nothing if `assetOutBalance` is Zero After Bidding

**File:** `src/AuctionBidder.sol`, lines 83-91

**Severity:** Low

**Description:**
After calling `auction.bid()`, the `AuctionBidder` checks its `assetOut` balance and transfers it to `s_receiver` if non-zero (lines 83-91). If the solution calls resulted in exact spending, the balance could be zero, and the transfer is silently skipped. This is expected behavior, but if the receiver is `address(0)`, the balance stays in the contract permanently (unless admin withdraws).

When `s_receiver == address(0)` (line 88), any `assetOut` tokens remaining in the AuctionBidder are effectively stranded until an admin calls `withdraw()`.

**Line References:**
- `AuctionBidder.sol:83-91` -- balance check and conditional transfer
- `AuctionBidder.sol:86-88` -- receiver zero check

---

## [L-06] `NativeTokenReceiver.receive()` Silently Swallows Failed Deposit

**File:** `src/NativeTokenReceiver.sol`, lines 48-55

**Severity:** Low

**Description:**
The `receive()` function uses `try/catch` to wrap native tokens (line 52). If the `deposit()` call fails, the native ETH is still received by the contract but remains unwrapped. This could lead to accounting issues if the contract assumes all value is in wrapped token form.

**Line References:**
- `NativeTokenReceiver.sol:52` -- `try s_wrappedNativeToken.deposit{value: msg.value}() {} catch {}`

---

## [L-07] `performUpkeep` Checks `hasFeeAggregator` Using Address Comparison but `transferForSwap` May Still Revert

**File:** `src/BaseAuction.sol`, lines 318-322

**Severity:** Low

**Description:**
`hasFeeAggregator` is determined by `address(s_feeAggregator) != address(this)` (line 318). If the fee aggregator is set to `address(this)`, no `transferForSwap` call is made. But if the fee aggregator is a different address, `transferForSwap` is called. If that external contract is paused or the assets are not allowlisted on the fee aggregator, the call will revert, preventing all auction starts even for assets that have sufficient balance locally.

This is a known dependency but could cause unexpected DoS of the auction system.

**Line References:**
- `BaseAuction.sol:318` -- `bool hasFeeAggregator = address(s_feeAggregator) != address(this)`
- `BaseAuction.sol:320-322` -- conditional transferForSwap

---

## [I-01] `isValidSignature` Receiver Check Uses `address(this)` -- Funds Accumulate in Auction Contract

**File:** `src/GPV2CompatibleAuction.sol`, line 138

**Severity:** Informational

**Description:**
The CowSwap order validation requires `order.receiver == address(this)` (line 138). This means all `buyToken` (assetOut) proceeds from CowSwap settlements are sent to the auction contract itself. These funds are then forwarded to `s_assetOutReceiver` when the auction ends (`_onAuctionEnd`, BaseAuction.sol lines 393-396).

This means assetOut funds accumulate in the auction contract during the auction lifetime rather than being sent directly to the receiver. If the contract is paused or the auction end fails, these funds could be temporarily locked.

**Line References:**
- `GPV2CompatibleAuction.sol:138` -- `order.receiver != address(this)`
- `BaseAuction.sol:393-396` -- forwarding on auction end

---

## [I-02] `_liveAuctionExists()` Iterates All Allowlisted Assets -- Gas Concern

**File:** `src/BaseAuction.sol`, lines 676-683

**Severity:** Informational

**Description:**
`_liveAuctionExists()` iterates through all allowlisted assets to check if any have a non-zero auction start. This is called by configuration functions (`_setAssetOut`, `_setAssetOutReceiver`, `_setFeeAggregator`, `_onFeedInfoUpdate`). With many allowlisted assets, this could become gas-expensive, though since these are all admin functions, this is primarily a concern for operational costs rather than security.

**Line References:**
- `BaseAuction.sol:676-683`

---

## [I-03] `startingPriceMultiplier` Can Equal `endingPriceMultiplier` -- Flat Price Auction

**File:** `src/BaseAuction.sol`, lines 650-657

**Severity:** Informational

**Description:**
The validation allows `startingPriceMultiplier == endingPriceMultiplier` (line 653 uses `>` not `>=`). This creates a flat-price auction where the price never decays. While this may be intentional, it means the auction has no time-pressure mechanism, potentially leading to no bids if the flat price is not competitive.

**Line References:**
- `BaseAuction.sol:653` -- `if (assetParams.endingPriceMultiplier > assetParams.startingPriceMultiplier)`
