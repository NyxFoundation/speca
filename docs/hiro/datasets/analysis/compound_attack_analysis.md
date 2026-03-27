# Compound Attack & Edge Case Analysis - Chainlink Payment Abstraction V2

## Analysis Date: 2026-03-26

---

## Finding 1 [MEDIUM]: GPV2CompatibleAuction `_onAuctionStart` approves current balance, but direct token transfers inflate approval enabling over-extraction by CowSwap solver

**Severity:** Medium
**Actor:** Permissionless (anyone can send ERC20 tokens to the contract)
**Files:** `GPV2CompatibleAuction.sol` L86-93, `BaseAuction.sol` L320-321

### Description

When `performUpkeep()` starts an auction, the flow is:
1. `s_feeAggregator.transferForSwap(address(this), eligibleAssets)` transfers assets to the auction contract (BaseAuction.sol L321)
2. `_onAuctionStart(asset)` is called (BaseAuction.sol L354)
3. In GPV2CompatibleAuction, `_onAuctionStart` approves the vault relayer for `IERC20(asset).balanceOf(address(this))` (GPV2CompatibleAuction.sol L92)

The approval is set to the **full balance at the time of auction start**. However, if someone sends tokens directly to the auction contract before `performUpkeep` is called, the approval will include those extra tokens. The CowSwap vault relayer can then pull the full approved amount.

More critically, after the auction starts, additional tokens can arrive (e.g., from a second `performUpkeep` call for the same asset if the first one included it in both `eligibleAssets` and `endedAuctions`, or from direct transfers). The approval is only set once at start and is **not** updated. The `bid()` function in BaseAuction transfers tokens to the bidder (L444), reducing the balance. But the CowSwap relayer approval remains at the original amount. If the auction hasn't been fully bid down via `bid()`, the CowSwap solver can pull the entire originally-approved amount.

This is distinct from M-14 (stale approval after `_setAuction`) because this is about the approval amount being inflated by direct token deposits before `performUpkeep`, not about approvals persisting after auction configuration changes.

### Impact

A permissionless attacker can send a small amount of an auctioned asset directly to the GPV2CompatibleAuction contract before `performUpkeep`. This inflates the vault relayer's approval. The CowSwap solver (which is a third-party entity) then has approval to pull more tokens than were intended for auction, potentially settling orders at stale/unfavorable prices for extra tokens that were not intended to be part of the auction.

### Lines

```solidity
// GPV2CompatibleAuction.sol L92
IERC20(asset).forceApprove(i_gpV2VaultRelayer, IERC20(asset).balanceOf(address(this)));
```

---

## Finding 2 [MEDIUM]: `bid()` is permissionless -- any address can call it, bypassing the AUCTION_BIDDER_ROLE trust boundary

**Severity:** Medium
**Actor:** Permissionless
**Files:** `BaseAuction.sol` L410-458

### Description

The `bid()` function in `BaseAuction.sol` has **no access control** -- it is callable by anyone (`external whenNotPaused`). This is by design for the Dutch auction pattern. However, the `AuctionBidder` contract's `bid()` function (L65-92) has the `AUCTION_BIDDER_ROLE` guard. This creates a split trust model:

- `AuctionBidder.bid()` requires `AUCTION_BIDDER_ROLE` (semi-trusted)
- `BaseAuction.bid()` is fully permissionless

Any external address can directly call `BaseAuction.bid()` without going through the `AuctionBidder`. They only need to:
1. Have enough `assetOut` tokens
2. Approve the auction contract
3. Call `bid(asset, amount, "")` (empty data, no callback)

This means the `AUCTION_BIDDER_ROLE` is not actually a security boundary for bidding -- it only gates the `AuctionBidder` contract's extra functionality (callback, solution execution, receiver forwarding). A permissionless caller can bid directly on the auction at the current Dutch auction price.

This is architecturally intentional but worth noting: the access control on `AuctionBidder.bid()` does NOT restrict who can participate in auctions. If the protocol assumes only AUCTION_BIDDER_ROLE holders can bid, this is a broken assumption.

**Note:** This may be intended design. Including because it has implications for compound attacks below.

---

## Finding 3 [MEDIUM]: `_getAssetOutAmount` division by zero when `assetOutUsdPrice` is zero (bypasses validation path)

**Severity:** Medium
**Actor:** Permissionless (triggered by oracle conditions)
**Files:** `BaseAuction.sol` L777-803

### Description

In `_getAssetOutAmount()` at line 802:
```solidity
return auctionUsdValue.mulDivUp(10 ** s_assetParams[s_assetOut].decimals, assetOutUsdPrice);
```

If `assetOutUsdPrice` is 0, this will revert with a division-by-zero panic. The `assetOutUsdPrice` is fetched at line 798:
```solidity
(uint256 assetOutUsdPrice,,) = _getAssetPrice(s_assetOut, withValidation);
```

When `withValidation` is `false` (as in the `getAssetOutAmount` view function at L766), `_getAssetPrice` can return `price = 0` without reverting. The zero price then flows into `mulDivUp` which will panic on division by zero.

This is distinct from M-01 (staleness causing revert) because:
- M-01 is about stale prices causing the `withValidation=true` path to revert
- This is about `withValidation=false` returning a zero price that causes an unhandled panic in the arithmetic

The `getAssetOutAmount()` external view (L749-767) explicitly uses `withValidation: false` and returns 0 for invalid auctions, but does NOT guard against zero `assetOutUsdPrice`. The function is likely used by off-chain systems to determine bid amounts, and an unhandled panic could cause unexpected behavior in integrating systems.

For `bid()` (which uses `withValidation: true`), this path is guarded. But for the GPV2CompatibleAuction `isValidSignature` path, the `_getAssetOutAmount` call at line 154 uses `withValidation: true`, so it's also guarded there.

### Impact

The `getAssetOutAmount()` view function will revert with a panic (not a clean error) when the assetOut oracle returns zero price while `withValidation=false`. This breaks any off-chain system or contract relying on this view function for price quotes.

### Lines

```solidity
// BaseAuction.sol L802
return auctionUsdValue.mulDivUp(10 ** s_assetParams[s_assetOut].decimals, assetOutUsdPrice);
```

---

## Finding 4 [MEDIUM]: GPV2 `isValidSignature` uses `block.timestamp` for price calculation, allowing solver to exploit price decay at exact auction boundary

**Severity:** Medium
**Actor:** CowSwap Solver (permissionless within CowSwap system)
**Files:** `GPV2CompatibleAuction.sol` L119-176, `BaseAuction.sol` L777-803

### Description

In `isValidSignature()` (GPV2CompatibleAuction.sol L148-154):
```solidity
uint256 elapsedTime = block.timestamp - auctionStart;
AssetParams memory assetParams = s_assetParams[address(order.sellToken)];
if (elapsedTime > assetParams.auctionDuration) {
    revert InvalidAuction(address(order.sellToken));
}
(uint256 sellTokenUsdPrice,,) = _getAssetPrice(address(order.sellToken), true);
uint256 minBuyAmount = _getAssetOutAmount(assetParams, sellTokenUsdPrice, order.sellAmount, elapsedTime, true);
```

The `elapsedTime` check at L150 uses `>` (strictly greater than), meaning at `elapsedTime == auctionDuration`, the order is still valid. At this exact boundary, `_getAssetOutAmount` clamps `elapsedTime` to `auctionDuration` (L785), and the price multiplier reaches its minimum (`endingPriceMultiplier`).

However, there is a race condition between `isValidSignature` validation and `performUpkeep` auction ending. The `checkUpkeep` function uses `<` for the duration check (L250: `auctionStart + assetParams.auctionDuration < block.timestamp`), which means the auction is considered ended when `block.timestamp > auctionStart + auctionDuration`. But `isValidSignature` considers the auction valid when `elapsedTime <= auctionDuration` (i.e., `block.timestamp <= auctionStart + auctionDuration`).

At `block.timestamp == auctionStart + auctionDuration`:
- `isValidSignature`: auction is VALID (elapsedTime == auctionDuration, not > auctionDuration)
- `checkUpkeep`: auction is NOT ended (`auctionStart + duration < block.timestamp` is false since they're equal)

This is consistent. But at `block.timestamp == auctionStart + auctionDuration + 1`:
- `isValidSignature`: auction is INVALID (reverts)
- `checkUpkeep`: auction IS ended

The real issue: CowSwap settlement is asynchronous. A solver can submit an order during the auction, and the CowSwap settlement contract calls `isValidSignature` at settlement time. If the solver submits at `elapsedTime == auctionDuration` (maximum discount) and the settlement lands in the same block, it gets the maximum discount. But if `performUpkeep` to end the auction is also called in the same block, the order could still be valid since `isValidSignature` doesn't check `s_entered` for GPV2 path -- it only checks it for reentrancy from `bid()`.

This is a timing edge case where a CowSwap order at maximum discount can be settled right at the auction boundary.

### Impact

CowSwap solvers can target the maximum discount point of the Dutch auction curve by submitting orders right at `auctionDuration`. The protocol always pays the endingPriceMultiplier discount at this boundary.

### Lines

```solidity
// GPV2CompatibleAuction.sol L148-151
uint256 elapsedTime = block.timestamp - auctionStart;
AssetParams memory assetParams = s_assetParams[address(order.sellToken)];
if (elapsedTime > assetParams.auctionDuration) {
    revert InvalidAuction(address(order.sellToken));
```

---

## Finding 5 [MEDIUM]: `_onAuctionEnd` transfers assetOut balance to receiver regardless of which auction ended, allowing cross-auction assetOut extraction

**Severity:** Medium
**Actor:** AUCTION_WORKER_ROLE (trusted, but impact is on fund accounting)
**Files:** `BaseAuction.sol` L379-397

### Description

When any auction ends, `_onAuctionEnd` at line 393-396 transfers ALL `assetOut` balance to the `assetOutReceiver`:

```solidity
uint256 assetOutBalance = IERC20(s_assetOut).balanceOf(address(this));
if (assetOutBalance > 0) {
    IERC20(s_assetOut).safeTransfer(s_assetOutReceiver, assetOutBalance);
}
```

If multiple auctions are running simultaneously (for different assets), and bids have been placed on some of them (resulting in `assetOut` accumulating in the contract), ending ANY single auction will sweep ALL accumulated `assetOut` -- including `assetOut` from bids on still-live auctions.

This is by design (the protocol wants `assetOut` forwarded to the receiver). But it creates an interesting accounting edge case: if `performUpkeep` ends auction A while auction B is still live, the `assetOut` from auction B's bids is also swept. This is correct behavior but worth noting for protocol accounting.

However, this has a real implication: **a permissionless bidder who bids on auction B right AFTER auction A is ended won't have their assetOut contribution immediately swept**. It will sit in the contract until the next auction end or the next `_onAuctionEnd` call. This is just protocol design, not a vulnerability.

**Downgraded from original assessment -- this is intended behavior, not a vulnerability.**

---

## Finding 6 [HIGH]: Compound Attack -- Permissionless bid() + token balance manipulation enables auction draining at favorable prices

**Severity:** High
**Actor:** Permissionless
**Files:** `BaseAuction.sol` L410-458, L437-440, `GPV2CompatibleAuction.sol` L86-93

### Description

This chains multiple observations:

1. `bid()` is permissionless (Finding 2)
2. `bid()` checks `amount > availableBalance` using `balanceOf(address(this))` at L437-438
3. The auction price decays over time (Dutch auction)
4. An attacker can send tokens directly to the contract to inflate `availableBalance`

Attack scenario:
1. An auction starts for token X with balance B (pulled from feeAggregator)
2. Attacker sends additional amount D of token X directly to the auction contract
3. Now `IERC20(asset).balanceOf(address(this))` returns `B + D`
4. Attacker bids for amount `B + D`, passing the balance check
5. Attacker receives `B + D` tokens of X
6. Attacker pays `assetOut` for the full `B + D` amount at the current (possibly discounted) Dutch auction price
7. Net result: attacker effectively "sells" `assetOut` to get the D tokens back (that they deposited) plus B tokens from the feeAggregator, all at the Dutch auction price

The attacker's cost is `assetOutAmount` for the full `B + D` bid. They get back `B + D` tokens. Their profit depends on whether the Dutch auction price is favorable enough. At the end of the auction (maximum discount), this is most profitable.

However, the attacker loses the D tokens they deposited AND pays assetOut for all B+D tokens. So the net is: they get B+D of assetIn and pay assetOutAmount. The D tokens wash (they deposited D, got D back as part of bid). So effectively they just bid B at the current price, which is normal auction behavior -- the extra D is a wash.

**After analysis: this is NOT a vulnerability.** The attacker's direct deposit inflates the balance but also inflates what they pay for. The economics don't create an exploit because the attacker pays fair auction price for all tokens received, including their own deposited tokens.

**RETRACTED -- not a valid finding.**

---

## Finding 7 [MEDIUM]: `checkUpkeep` uses stale/zero prices for USD value calculation without validation, can cause auctions to start or not end correctly

**Severity:** Medium
**Actor:** Permissionless (oracle-driven)
**Files:** `BaseAuction.sol` L238, L248, L258

### Description

In `checkUpkeep()`, prices are fetched with `withValidation: false` (L238):
```solidity
(uint256 assetPrice,, bool isPriceValid) = _getAssetPrice(asset, false);
```

For the auction-end check at L248:
```solidity
uint256 assetBalanceUsdValue = (assetBalance * assetPrice) / (10 ** assetParams.decimals);
```

If `assetPrice` is 0 (stale/zero oracle), then `assetBalanceUsdValue` will be 0, which is always `< assetParams.minAuctionSizeUsd`. This means the auction would be flagged as ended (L251) when it shouldn't be -- the price is just temporarily unavailable.

However, this is gated by `isPriceValid` at L251:
```solidity
|| (isPriceValid && assetBalanceUsdValue < assetParams.minAuctionSizeUsd)
```

Wait -- looking more carefully: the duration check `auctionStart + assetParams.auctionDuration < block.timestamp` has NO price validity gate. If the duration has passed, the auction is ended regardless. The price-based early ending IS gated by `isPriceValid`. So the zero-price case for early ending is actually handled.

But for the auction START path at L258:
```solidity
uint256 availableAssetUsdValue = (availableBalance * assetPrice) / (10 ** assetParams.decimals);
if (availableAssetUsdValue >= assetParams.minAuctionSizeUsd) {
```

This is gated by `isPriceValid` at L255 (`else if (isPriceValid)`). So zero prices won't start auctions either.

**After analysis: the `isPriceValid` checks properly gate both paths. NOT a vulnerability.**

**RETRACTED.**

---

## Finding 8 [MEDIUM]: `startingPriceMultiplier` can equal `endingPriceMultiplier`, making `auctionDuration` effectively a flat-price auction with no decay -- `mulDiv` with 0 numerator and non-zero denominator is fine but misleading

**Severity:** Low/Informational
**Actor:** ASSET_ADMIN_ROLE (trusted)
**Files:** `BaseAuction.sol` L650-657, L793-795

### Description

The validation at L653 is:
```solidity
if (assetParams.endingPriceMultiplier > assetParams.startingPriceMultiplier) {
    revert ...
}
```

This allows `endingPriceMultiplier == startingPriceMultiplier`. In `_getAssetOutAmount` L794:
```solidity
uint256(assetInParams.startingPriceMultiplier - assetInParams.endingPriceMultiplier).mulDiv(elapsedTime, assetInParams.auctionDuration)
```

When equal, the subtraction is 0, so `mulDiv(0, elapsedTime, auctionDuration)` = 0. The price multiplier stays constant. This is valid behavior (flat-price auction) but worth noting.

**This is informational, not a vulnerability.**

---

## Finding 9 [MEDIUM]: `bid()` transfers asset to `msg.sender` BEFORE callback, enabling callback to observe inflated assetOut requirements

**Severity:** Medium
**Actor:** Permissionless (via bid()) or AUCTION_BIDDER_ROLE (via AuctionBidder)
**Files:** `BaseAuction.sol` L444-453

### Description

In `bid()`:
```solidity
IERC20(asset).safeTransfer(msg.sender, amount);  // L444

// If the caller has specified data.
if (data.length != 0) {
    IAuctionCallback(msg.sender).auctionCallback(msg.sender, assetOut, assetOutAmount, data);  // L449
}

// Pull assetOut from the caller.
IERC20(assetOut).safeTransferFrom(msg.sender, address(this), assetOutAmount);  // L453
```

The reentrancy guard (`s_entered`) prevents calling `bid()` again. But the callback at L449 executes arbitrary code via `_multiCall` in AuctionBidder. The callback receives the auctioned asset first (L444), then must approve/provide assetOut (L453).

This is the intended flash-loan-like pattern: receive asset first, do something with it, then pay assetOut. The reentrancy guard properly prevents re-entering `bid()`.

However, the `isValidSignature` function in GPV2CompatibleAuction (L125) checks `s_entered`:
```solidity
if (s_entered) {
    revert Errors.ReentrantCall();
}
```

This means during a `bid()` callback, CowSwap orders cannot be validated. This is intentional and correct -- it prevents concurrent bid+CowSwap settlement.

**No vulnerability here -- the pattern is correctly implemented with reentrancy protection.**

---

## Finding 10 [HIGH]: GPV2CompatibleAuction `isValidSignature` does not check `minBidUsdValue`, allowing CowSwap micro-orders that bypass minimum bid

**Severity:** High
**Actor:** CowSwap Solver (permissionless within CowSwap system)
**Files:** `GPV2CompatibleAuction.sol` L119-176, `BaseAuction.sol` L430-435

### Description

The `bid()` function enforces a minimum bid USD value (BaseAuction.sol L430-435):
```solidity
uint256 bidUsdValue = (amount * assetPrice) / (10 ** assetParams.decimals);
uint88 minBidUsdValue = s_minBidUsdValue;
if (bidUsdValue < minBidUsdValue) {
    revert BidValueTooLow(bidUsdValue, minBidUsdValue);
}
```

However, `isValidSignature()` in GPV2CompatibleAuction does NOT enforce this minimum. It validates:
- Sell token is a valid auction (L131-134)
- Buy token is assetOut (L135-137)
- Receiver is the contract itself (L138-140)
- Sell amount > 0 (L141-143)
- Sell amount <= balance (L144-147)
- Buy amount >= minBuyAmount from price curve (L153-157)
- Order not expired (L158-160)
- Various order format checks

But there is NO check equivalent to `minBidUsdValue`. A CowSwap solver can create valid orders for arbitrarily small amounts (as long as `sellAmount > 0`). This enables:

1. **Dust attacks**: Many tiny orders can drain the auction balance in small increments
2. **Gas griefing**: The auction ends when balance drops below `minAuctionSizeUsd` (in `checkUpkeep`), but many small CowSwap fills can reduce the balance gradually
3. **Bypassing the minimum bid protection**: The `minBidUsdValue` is a protocol parameter set to prevent economically inefficient trades, but CowSwap orders completely bypass it

### Impact

CowSwap solvers can fill auction orders in arbitrarily small amounts, bypassing the `minBidUsdValue` protection. This can lead to:
- Dust accumulation in the auction contract
- Economic inefficiency (many small trades instead of fewer large ones)
- Potential for more sophisticated extraction at maximum discount with many small orders timed at `auctionDuration`

### Lines

```solidity
// GPV2CompatibleAuction.sol L119-176 -- no minBidUsdValue check
// Compare with BaseAuction.sol L430-435 -- has minBidUsdValue check
```

---

## Finding 11 [MEDIUM]: `_getAssetOutAmount` uses `s_assetParams[s_assetOut].decimals` without checking if assetOut params are configured -- potential zero-exponent

**Severity:** Medium
**Actor:** Permissionless (via `getAssetOutAmount` view) or bidder
**Files:** `BaseAuction.sol` L802

### Description

At line 802:
```solidity
return auctionUsdValue.mulDivUp(10 ** s_assetParams[s_assetOut].decimals, assetOutUsdPrice);
```

If `s_assetParams[s_assetOut].decimals` is 0 (assetOut params not configured), then `10 ** 0 = 1`. The function would return `auctionUsdValue / assetOutUsdPrice`, which is incorrect scaling.

The `whenAssetOutConfigured` modifier on `performUpkeep` and `checkUpkeep` guards against this at the entry point level. And `bid()` does NOT have this modifier but relies on the auction being started (which requires `performUpkeep` to have run, which does check).

However, the `getAssetOutAmount()` external view at L749 also does NOT have the `whenAssetOutConfigured` modifier. If called before assetOut params are configured, it would return incorrectly scaled values.

### Impact

The `getAssetOutAmount()` view function can return incorrectly scaled amounts if called before `assetOut` params are configured. Off-chain systems relying on this could compute wrong bid amounts.

### Lines

```solidity
// BaseAuction.sol L802
return auctionUsdValue.mulDivUp(10 ** s_assetParams[s_assetOut].decimals, assetOutUsdPrice);
```

---

## Finding 12 [MEDIUM]: GPV2 order `receiver` must be `address(this)` but `_onAuctionEnd` sends assetOut to `s_assetOutReceiver` -- CowSwap assetOut stays in contract until next auction end

**Severity:** Medium
**Actor:** Permissionless (timing-dependent)
**Files:** `GPV2CompatibleAuction.sol` L138-140, `BaseAuction.sol` L393-396

### Description

GPV2 `isValidSignature` requires `order.receiver == address(this)` (L138-140). This means CowSwap settlements send the `buyToken` (assetOut) to the auction contract itself.

The assetOut is only swept to `s_assetOutReceiver` during `_onAuctionEnd` (L393-396). Between CowSwap settlement and auction end, the assetOut sits in the contract.

During this window:
- If a `bid()` is called, it uses `safeTransferFrom` to pull assetOut from the bidder (L453), so the existing assetOut balance is not affected
- But `_onAuctionEnd` sweeps ALL assetOut balance, including from CowSwap settlements

This is intended behavior. However, the GPV2 vault relayer approval is set to the INITIAL balance (at auction start). After CowSwap settles some orders (reducing the sellToken balance), the remaining approval may exceed the remaining balance. This is fine because `transferFrom` is limited by `min(allowance, balance)`.

**After analysis: this is intended design. NOT a vulnerability.**

**RETRACTED.**

---

## Summary of Valid New Findings

| # | Severity | Title | Actor |
|---|----------|-------|-------|
| 1 | Medium | GPV2 `_onAuctionStart` approval inflated by direct token deposits | Permissionless |
| 3 | Medium | `getAssetOutAmount` view panics on zero assetOut price | Permissionless (oracle) |
| 4 | Medium | CowSwap solver can target max-discount boundary timing | CowSwap Solver |
| **10** | **High** | **GPV2 `isValidSignature` missing `minBidUsdValue` check** | **CowSwap Solver** |
| 11 | Medium | `getAssetOutAmount` view returns wrong scaling when assetOut not configured | Permissionless |

### Retracted (not vulnerabilities after deeper analysis)

| # | Reason |
|---|--------|
| 2 | Permissionless `bid()` is by design |
| 5 | Cross-auction assetOut sweep is by design |
| 6 | Token balance inflation doesn't create economic advantage |
| 7 | `isPriceValid` checks properly gate both paths |
| 8 | Flat-price auction is valid configuration |
| 9 | Reentrancy protection is correctly implemented |
| 12 | CowSwap receiver pattern is by design |

### Compound Attack Chains Analyzed

1. **M-01 + M-02 compound**: Both relate to oracle staleness. M-01 (staleness DoS on bid/performUpkeep) and M-02 (shared stalenessThreshold for dual oracle) could compound: if Data Streams is down and the data feed uses a different staleness requirement, the shared threshold could either be too strict (causing DoS) or too lax (accepting stale prices). However, this is already captured by M-02's description. No new compound vector found beyond what's described.

2. **H-01 + Finding 10 compound**: H-01 (unrestricted _multiCall in auctionCallback) combined with the missing minBidUsdValue in GPV2 could allow: an AUCTION_BIDDER_ROLE holder executes a bid via the callback to set up state, then a CowSwap solver fills micro-orders. However, these are independent issues and don't create a worse combined impact.

3. **Finding 1 + Finding 10 compound**: Inflated vault relayer approval (Finding 1) + missing minBidUsdValue check (Finding 10) means a CowSwap solver can: (a) observe extra tokens sent to the contract, (b) create many small orders to drain the inflated balance at maximum discount without hitting any minimum size guard. This is the most concerning compound: the inflated balance from direct deposits can be drained via small CowSwap orders at the endingPriceMultiplier discount.
