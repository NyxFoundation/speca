# Chainlink Payment Abstraction V2 - Arithmetic Edge Case Audit

## Files Analyzed

- `src/BaseAuction.sol` - `_getAssetOutAmount` (L777-803), `bid()` (L410-458), `checkUpkeep` (L216-294), constructor (L179-200), `_setMinBidUsdValue` (L474-486), asset param validation (L630-664)
- `src/GPV2CompatibleAuction.sol` - `isValidSignature` (L119-176)
- `src/PriceManager.sol` - `_getAssetPrice` (L372-419)

## Excluded (Already Found)

M-01, M-02, M-03, M-07, M-15, H-01

---

## Scenario 1: Zero/Dust assetOutAmount via Rounding Up

### Trace

Given:
- `assetInUsdPrice = 1` (1 wei, manipulated/low-cap oracle)
- `amount = 1` (1 wei of assetIn, 18 decimals)

Step 1: `amountIn.mulDivUp(assetInUsdPrice, 10**decimals)`
```
mulDivUp(1, 1, 10^18) = ceil(1 / 10^18) = 1
```
Solady `mulDivUp` rounds up, so `auctionUsdValue_before_multiplier = 1`.

Step 2: `.mulWadUp(priceMultiplier)` where priceMultiplier ~= 1e18 (e.g., `startingPriceMultiplier`)
```
mulWadUp(1, 1e18) = ceil(1 * 1e18 / 1e18) = 1
```
So `auctionUsdValue = 1`.

Step 3: `auctionUsdValue.mulDivUp(10**assetOutDecimals, assetOutUsdPrice)`
If assetOut = LINK (18 decimals, price = 20e18):
```
mulDivUp(1, 10^18, 20e18) = ceil(10^18 / (20 * 10^18)) = ceil(0.05) = 1
```
So `assetOutAmount = 1 wei of LINK`.

### Impact Assessment

**In `bid()`**: Protected. Line 430 computes `bidUsdValue = (amount * assetPrice) / (10 ** decimals)` = `(1 * 1) / 10^18 = 0`. The `minBidUsdValue` check at L433 (must be > 0 per `_setMinBidUsdValue`) would revert. **No vulnerability via `bid()`.**

**In `isValidSignature()` (GPV2CompatibleAuction L119-176)**: There is NO `minBidUsdValue` check. The CowSwap settlement path calls `_getAssetOutAmount` directly at L154 and only checks that `order.buyAmount >= minBuyAmount`. The `sellAmount` can be as low as 1 wei (only checked against `sellAmount == 0` at L141 and `sellAmount <= balance` at L145).

However, this is already captured by **M-15** (which covers the missing minBidUsdValue check in isValidSignature). The rounding amplifies the M-15 impact: with 3 chained round-up operations, the attacker gets 1 wei of LINK per 1 wei of dust token, but the absolute value extracted is negligible (fractions of a cent). The CowSwap solver/gas costs far exceed the extractable value.

**Verdict: LOW / Informational** -- The rounding-up favors the bidder but the absolute extraction is negligible. The missing `minBidUsdValue` check in `isValidSignature` (M-15) is the actual gate; this scenario merely provides a concrete trace for that finding.

---

## Scenario 2: Maximum Extraction via Rounding

### Analysis

The `_getAssetOutAmount` function chains three round-up operations:
1. `mulDivUp(amountIn, assetInUsdPrice, 10**decimals)` -- rounds up by at most 1
2. `mulWadUp(result, priceMultiplier)` -- rounds up by at most 1
3. `mulDivUp(auctionUsdValue, 10**assetOutDecimals, assetOutUsdPrice)` -- rounds up by at most 1

Each `mulDivUp`/`mulWadUp` adds at most 1 wei to the result. But the rounding compounds: the +1 from step 1 is then multiplied in step 2, and the +1 from step 2 is then multiplied in step 3.

Worst-case compound analysis:
- Step 1 result: `trueValue_1 + 1`
- Step 2 input is `trueValue_1 + 1`, result: `(trueValue_1 + 1) * priceMultiplier / 1e18 + 1`
- The +1 from step 1 contributes `priceMultiplier / 1e18` extra (at most ~1.8e19/1e18 ~= 18 given uint64 max for priceMultiplier)
- Step 3 multiplies by `10^assetOutDecimals / assetOutUsdPrice`, which can amplify further if `assetOutUsdPrice` is small

For realistic parameters (LINK at $20, priceMultiplier around 1e18):
- Max rounding = ~3 wei of assetOut
- Value: 3 wei of LINK = negligible

For adversarial but valid parameters (priceMultiplier = type(uint64).max ~= 1.8e19, assetOutUsdPrice = 1e18 i.e. $1):
- Step 1 rounding contributes: 1 * 1.8e19 / 1e18 = 18 wei extra to step 2
- Step 2 rounding: +1
- Step 3 amplification: (18 + 1) * 10^18 / 1e18 + 1 = 20 wei
- Still negligible value

**Verdict: NOT A FINDING** -- Maximum extractable rounding is on the order of tens of wei of assetOut, worth fractions of a cent.

---

## Scenario 3: priceMultiplier = 0

### Constructor Bounds

From the constructor (L193-197):
```solidity
if (params.minPriceMultiplier == 0) {
    revert Errors.InvalidZeroValue();
}
i_minPriceMultiplier = params.minPriceMultiplier;
```

`i_minPriceMultiplier` is `uint64`, must be >= 1.

From asset param validation (L650-657):
```solidity
if (assetParams.endingPriceMultiplier < i_minPriceMultiplier) {
    revert InvalidEndingPriceMultiplier(...);
}
if (assetParams.endingPriceMultiplier > assetParams.startingPriceMultiplier) {
    revert StartingPriceMultiplierLowerThanEndingPriceMultiplier(...);
}
```

So: `endingPriceMultiplier >= i_minPriceMultiplier >= 1` and `startingPriceMultiplier >= endingPriceMultiplier >= 1`.

### Can priceMultiplier reach 0 at runtime?

The formula at L793-795:
```solidity
uint256 priceMultiplier = assetInParams.startingPriceMultiplier
    - uint256(assetInParams.startingPriceMultiplier - assetInParams.endingPriceMultiplier)
      .mulDiv(elapsedTime, assetInParams.auctionDuration);
```

When `elapsedTime = auctionDuration`:
```
priceMultiplier = start - (start - end) * duration / duration = start - (start - end) = end
```

Since `end >= 1`, priceMultiplier is always >= 1.

When `startingPriceMultiplier == endingPriceMultiplier`:
```
priceMultiplier = start - 0 = start >= 1
```

**Edge case**: `startingPriceMultiplier = endingPriceMultiplier = 1` (i.e., i_minPriceMultiplier = 1).
Then `priceMultiplier = 1` at all times.
In `mulWadUp(auctionUsdValue, 1)` = `ceil(auctionUsdValue * 1 / 1e18)`.
For any `auctionUsdValue < 1e18`, this rounds up to 1.
For `auctionUsdValue = 0`, this returns 0.

With `priceMultiplier = 1` (not 1e18!), the auction effectively prices the assetIn at 1/1e18th of its USD value. This is a massive discount (essentially free). However, deploying with `i_minPriceMultiplier = 1` would be an extreme misconfiguration -- the parameter description says "e.g. 0.98e18 represents a maximum discount of 2%".

**Verdict: CONFIGURATION RISK (Informational)** -- There is no lower bound enforced on `i_minPriceMultiplier` beyond `!= 0`. A value of `1` would create a ~100% discount. This is an admin configuration error, not a code vulnerability. The constructor comment and example values (0.98e18) make the intended range clear. A minimum bound (e.g., `>= 0.5e18`) would prevent misconfiguration.

---

## Scenario 4: Huge assetOutAmount Overflow in _getAssetOutAmount

### Analysis

All arithmetic in `_getAssetOutAmount` uses Solady's `mulDivUp`/`mulWadUp`, which use 512-bit intermediate products. These functions revert on overflow of the final uint256 result (Solady's `mulDivUp` reverts if the quotient exceeds `type(uint256).max`).

Can the result overflow?

Worst case:
- `assetInUsdPrice`: Prices are scaled to 18 decimals. Even BTC at $100k = 100_000e18 = 1e23. Max realistic: ~1e30 (for extreme edge).
- `amountIn`: Bounded by `balanceOf(address(this))`. For 18-decimal token: max realistic ~1e30 (billion tokens).
- `assetOutUsdPrice`: Minimum is 1 (after scaling). Realistically > 1e14 (sub-cent token).

Step 1: `mulDivUp(1e30, 1e30, 1e18)` = ~1e42.
Step 2: `mulWadUp(1e42, 1.8e19)` = ~1.8e43. (uint64 max multiplier)
Step 3: `mulDivUp(1.8e43, 1e18, 1)` = 1.8e61.

`type(uint256).max` ~= 1.15e77. So even with extreme values, no overflow.

To actually overflow: need `auctionUsdValue * 10^assetOutDecimals > type(uint256).max * assetOutUsdPrice`. With `assetOutUsdPrice >= 1` and `assetOutDecimals <= 18`, we need `auctionUsdValue > 1.15e59`. This would require absurd input values far beyond any realistic token supply.

**Verdict: NOT A FINDING** -- No realistic overflow possible in `_getAssetOutAmount`. Solady handles 512-bit intermediates and reverts on overflow.

---

## Scenario 5: Unchecked Multiplication Overflow in bid() L430

### The Bug

```solidity
uint256 bidUsdValue = (amount * assetPrice) / (10 ** assetParams.decimals);  // L430
```

This uses **native Solidity 0.8.x checked arithmetic**, NOT Solady's `mulDiv`. The multiplication `amount * assetPrice` can overflow `uint256` and **revert** (Solidity 0.8+ reverts on overflow by default).

### Can this cause a revert-based DoS?

- `amount` is bounded by `IERC20(asset).balanceOf(address(this))` at L437-441.
- `assetPrice` is scaled to 18 decimals.

For a standard 18-decimal token:
- Max realistic balance: ~1e30 (1 trillion tokens with 18 decimals)
- assetPrice at 18 decimals: even 1e23 (high-value token)
- Product: 1e30 * 1e23 = 1e53. Well under `type(uint256).max` (~1.15e77).

For a **0-decimal token** (e.g., some NFT-like ERC20s):
- Theoretical balance: up to `type(uint256).max` (~1.15e77)
- assetPrice: even 1e18 (a $1 token)
- Product: 1.15e77 * 1e18 = 1.15e95 > `type(uint256).max` -- **OVERFLOW AND REVERT**

However, `amount` is first used at L430 for the USD value check, then compared to `availableBalance` at L437-441. The check order is:

```solidity
uint256 bidUsdValue = (amount * assetPrice) / (10 ** assetParams.decimals);  // L430 - can revert here
...
uint256 availableBalance = IERC20(asset).balanceOf(address(this));           // L437
if (amount > availableBalance) {                                             // L438
    revert BidAmountTooHigh(amount, availableBalance);
}
```

The overflow revert at L430 happens **before** the balance check at L437. A malicious bidder could pass `amount = type(uint256).max` and cause an overflow revert. But this is just a revert -- the bidder only DoS-es their own transaction. They cannot pass `amount > balance` without the function reverting anyway (either at L430 or L438).

**The real question**: Can a legitimate bid with `amount <= balance` trigger the overflow?

For 0-decimal token with balance B:
- `B * assetPrice` overflows when `B > type(uint256).max / assetPrice`
- With `assetPrice = 1e18`: overflow when `B > 1.15e59`
- For any ERC20 with `totalSupply <= 2^128` (which covers all realistic tokens): max `B` = 2^128 = 3.4e38, product = 3.4e56, no overflow.
- Only tokens with extreme supplies (> 1e59 units at 0 decimals) with $1+ prices could trigger this.

**For `checkUpkeep` L248**: Same pattern:
```solidity
uint256 assetBalanceUsdValue = (assetBalance * assetPrice) / (10 ** assetParams.decimals);
```
Same analysis applies. `checkUpkeep` is a `view` function called by Chainlink Automation. An overflow here would cause the upkeep check to revert, meaning the automation would fail to detect auctions that should start or end.

The critical difference: `checkUpkeep` iterates ALL allowlisted assets. If ANY single asset triggers the overflow, the ENTIRE `checkUpkeep` reverts, blocking ALL auctions (not just the problematic one).

### Impact Assessment

**bid() L430**: Low risk. The overflow causes a revert that only affects the individual bid. The bidder can simply use a smaller `amount`. No funds at risk.

**checkUpkeep() L248**: Medium risk. If an allowlisted token somehow accumulates a balance large enough to overflow when multiplied by its price, the entire `checkUpkeep` function reverts, blocking Chainlink Automation from starting or ending ANY auction. However, this requires an extremely unusual token (0 decimals with > 1e59 supply), which is unlikely to be allowlisted.

**Verdict: LOW** -- The native multiplication at L430 and L248 can theoretically overflow for extreme token parameters, but realistic tokens with standard supplies are safe. The `bid()` overflow is self-DoS only. The `checkUpkeep()` overflow could block automation but requires an implausible token. Using `FixedPointMathLib.mulDiv` instead of native `*` would eliminate the theoretical risk at minimal gas cost.

---

## Scenario 6: checkUpkeep L248 - Same Unchecked Pattern

Covered in Scenario 5 above. Same `(balance * price) / (10 ** decimals)` pattern. Same theoretical overflow. Additionally present at L258:

```solidity
uint256 availableAssetUsdValue = (availableBalance * assetPrice) / (10 ** assetParams.decimals);
```

Here `availableBalance` comes from `IERC20(asset).balanceOf(feeAggregator)`, which could also be large. Same risk profile as L248.

**Key difference from `bid()`**: In `checkUpkeep`, the overflow would DoS the Chainlink Automation upkeep for ALL assets, not just one transaction. This is a broader blast radius.

---

## Summary of New Findings

| ID | Scenario | Severity | Status |
|----|----------|----------|--------|
| 1 | Dust rounding in `_getAssetOutAmount` | Informational | Subsumed by M-15 |
| 2 | Maximum rounding extraction | Informational | Max ~20 wei, negligible |
| 3 | priceMultiplier = 0/1 | Informational | Admin misconfiguration only |
| 4 | `_getAssetOutAmount` overflow | Not a Finding | Solady handles 512-bit; reverts on overflow |
| 5 | `bid()` L430 native multiplication overflow | Low | Self-DoS only; requires implausible token |
| 6 | `checkUpkeep()` L248/258 native multiplication overflow | Low | Could DoS automation; requires implausible token |

### Recommendation for Scenarios 5+6

Replace native multiplication with Solady `mulDiv` at:
- `BaseAuction.sol` L430: `uint256 bidUsdValue = amount.mulDiv(assetPrice, 10 ** assetParams.decimals);`
- `BaseAuction.sol` L248: `uint256 assetBalanceUsdValue = assetBalance.mulDiv(assetPrice, 10 ** assetParams.decimals);`
- `BaseAuction.sol` L258: `uint256 availableAssetUsdValue = availableBalance.mulDiv(assetPrice, 10 ** assetParams.decimals);`

This is a defensive hardening measure. The contract already imports and uses Solady `FixedPointMathLib` elsewhere (L795, L799, L802), so the inconsistency in L430/L248/L258 is notable.
