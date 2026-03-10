# Asymmetric oracle deviation check allows dangerous operations during debt token price spikes

## Summary

`get_price_with_check` computes the EMA-spot deviation by always dividing by `spot_price_value`, creating an asymmetry where upward price spikes (spot > EMA) produce smaller deviation values than downward crashes (EMA > spot) of equal magnitude. This allows borrowing/withdrawal operations to proceed during dangerous debt token spike periods when the deviation check should revert.

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

1. Market conditions need to create a significant spot price spike for a debt token (e.g., stablecoin depeg upward, volatile asset spike).

## Attack Path

1. Debt Token Y's spot price spikes to 2x its EMA (e.g., from volatile market conditions or oracle lag).
2. A borrower has an obligation with Debt Token Y. The EMA-based health check in `debts_value_usd_non_liquidation` (line 1198) uses `get_price_with_check` to value the debt.
3. Because the deviation check divides by the large spot price, the computed divergence is only 50% instead of the true 100%. With default tolerance of 10% (`DEFAULT_EMA_SPOT_DIFF_TOLERANCE_BPS = 1000`), a spike above 10% should revert — but the asymmetry means a ~22% spike (spot/EMA = 1.22) computes as only ~18% divergence, passing a 20% tolerance.
4. The EMA price (lower than spot) is used for debt valuation in the health check, **understating the true debt obligation**.
5. The borrower's position appears healthier than it actually is, allowing them to borrow more or withdraw collateral.
6. When EMA catches up to the true (higher) debt value, the position becomes undercollateralized.
7. The protocol accumulates bad debt from positions that should have been blocked during the spike.

**Note on collateral spikes**: When a collateral token's spot price spikes upward, EMA undervalues the collateral — this makes the position appear *less* healthy, which is conservative and safe. The dangerous direction is debt token spikes, where EMA undervalues the debt obligation.

## Impact

The deviation check is more lenient during upward price spikes — specifically dangerous for debt tokens where EMA undervaluation allows excessive borrowing against understated obligations. When the EMA catches up or the price reverts, these positions become undercollateralized.

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

## Severity Upgrade Note (Medium → High)

This finding should be considered for High severity because:
- **Dangerous direction**: The asymmetry specifically makes the check more lenient during debt token price spikes — the exact scenario where strict protection is needed. Collateral spikes are naturally conservative (EMA undervalues collateral, making positions appear less healthy).
- **Bad debt accumulation**: During debt token spikes, EMA-based debt valuation understates true obligations, allowing borrowers to take positions that become undercollateralized when EMA catches up. This creates protocol-level bad debt.
- **Scalable impact**: At 3x divergence, the check is 3x more lenient than intended. The asymmetry grows with divergence magnitude, providing the least protection during the most volatile conditions.
- **No attacker action needed**: Natural market volatility triggers this. Any debt token price spike above the tolerance threshold is inadequately filtered.

Per Sherlock criteria, a bug that enables systematic bad debt accumulation (loss of funds for the protocol/lenders) during foreseeable market conditions qualifies as High.

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
