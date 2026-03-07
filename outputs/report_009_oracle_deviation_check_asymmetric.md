# Borrower will avoid liquidation during price spikes due to asymmetric oracle deviation check

## Summary

`get_price_with_check` computes the EMA-spot deviation by always dividing by `spot_price_value`, creating an asymmetry where price spikes (spot > EMA) produce smaller deviation values than price crashes (EMA > spot) of equal magnitude, allowing operations to proceed during dangerous divergence periods when the check should revert.

## Root Cause

In [`user.move:50-54`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/x_oracle/sources/entry_points/user.move#L50-L54):

```move
let abs_diff = if (ema_price_value.gt(spot_price_value)) {
    ema_price_value.sub(spot_price_value).div(spot_price_value)
} else {
    spot_price_value.sub(ema_price_value).div(spot_price_value)
};
```

Both branches divide by `spot_price_value`. The mathematically symmetric formula would divide by the average or by `ema_price_value` in the second branch. The current formula produces:

- **Price crash** (EMA = 200, spot = 100): `(200 - 100) / 100 = 100%` — correctly detected as large divergence.
- **Price spike** (EMA = 100, spot = 200): `(200 - 100) / 200 = 50%` — appears as only 50% divergence.

For a `max_diff_allowed` of 50%, a 2x price spike passes the check while a 2x price crash correctly fails.

## Internal Pre-conditions

1. `get_price_with_check` needs to be called with a `max_diff_allowed` that is above the asymmetrically-reduced divergence value (e.g., >50%).
2. This function is used on the non-liquidation paths: `collaterals_usd_non_liquidation` (line 1280) and `debts_value_usd_non_liquidation` (line 1198).

## External Pre-conditions

1. Market conditions need to create a significant spot price spike for a collateral or debt token (e.g., LST depeg upward, flash crash recovery).

## Attack Path

1. Token X's spot price spikes to 2x its EMA (e.g., from oracle manipulation or volatile market).
2. A borrower has deposited Token X as collateral with outstanding debt.
3. The borrower calls `withdraw` or `borrow` — these paths use `get_price_with_check`.
4. The deviation check computes `(2x - 1x) / 2x = 50%`. With default `max_diff_allowed` set at a reasonable tolerance, this passes.
5. The EMA price (1x) is used for the health check, making the obligation appear healthy at the old (lower) collateral value.
6. The borrower withdraws collateral or borrows more, leaving the obligation undercollateralized when the EMA catches up to the actual price.
7. Conversely, when the spot price reverts, the EMA (still lagging high) prevents timely liquidation of the now-underwater position.

## Impact

The deviation check is more lenient during price spikes — exactly when it should be strictest. A borrower can take additional risk (withdraw collateral or borrow more) during transient price spikes because the asymmetric check underestimates the true divergence. When the spike reverts, the borrower's position becomes undercollateralized.

The severity scales with the magnitude of the divergence: at 3x spot/EMA ratio, the computed deviation is only 67% instead of the true 200%, making the check 3x more lenient than intended.

## PoC

Mathematical comparison:

| Scenario | Spot | EMA | True Divergence | Computed (÷ spot) |
|----------|------|-----|-----------------|-------------------|
| 2x crash | 100 | 200 | 100% | **100%** |
| 2x spike | 200 | 100 | 100% | **50%** |
| 3x crash | 100 | 300 | 200% | **200%** |
| 3x spike | 300 | 100 | 200% | **67%** |

The asymmetry grows with divergence magnitude.

## Mitigation

Either:
1. Use symmetric calculation by dividing by the denominator appropriate to each branch:
```move
let abs_diff = if (ema_price_value.gt(spot_price_value)) {
    ema_price_value.sub(spot_price_value).div(spot_price_value)   // crash: div by spot (smaller)
} else {
    spot_price_value.sub(ema_price_value).div(ema_price_value)    // spike: div by EMA (smaller)
};
```
2. Use the minimum of the two prices as the divisor in both branches: `div(min(ema, spot))`.
3. Use the average: `div((ema + spot) / 2)`.
