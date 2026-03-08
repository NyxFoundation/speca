# Liquidation bot will cause excessive collateral loss to barely-unhealthy obligation holders

## Summary

`ensure_liquidate_borrow_allowed` uses a static `close_factor` (e.g., 50%) to cap repayment instead of dynamically computing the minimum amount needed to restore health, causing borrowers with barely-unhealthy positions to lose up to 50% of their debt in collateral plus liquidation incentive when a fraction of a percent repayment would have been sufficient.

## Root Cause

In [`market.move:1008-1011`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L1008-L1011), the maximum repay amount is calculated as:

```
let max_debt_amount = debt_balance.mul(liquidation_params.close_factor);
```

This is a static percentage of total debt, not the dynamic minimum amount needed to restore the obligation to a healthy state. The module's own documentation at [`liquidate.move:2`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/lending/liquidate.move#L2) states: "adopts soft liquidation. Liquidation amount should be no bigger than the amount that would decrease the risk level of obligation to 1."

The implementation violates this soft liquidation invariant. A dynamic cap should compute `R_max` — the exact repay amount that would bring `weighted_debts_value` down to equal `collateral_weighted_value` (the liquidation threshold). Instead, the static close factor allows liquidation of far more than necessary.

## Internal Pre-conditions

1. `close_factor` in `MarketConfiguration` needs to be set to a value significantly greater than the minimum repay fraction needed to restore health (e.g., the typical 50% close factor).
2. The target obligation needs to be barely unhealthy — `weighted_debts_value` just barely exceeds `collateral_weighted_value` (by epsilon).
3. The obligation's `debt_value` needs to be above `close_factor_bypass_min_value` for the close factor to be enforced at all.
4. The obligation's `collateral_total_value` needs to be above `bad_debt_threshold` (101% of `debts_total_value`) so the bad debt bypass doesn't trigger.

## External Pre-conditions

1. Oracle price movement needs to cause the obligation to become barely unhealthy (e.g., collateral price drops slightly or debt price increases slightly).

## Attack Path

1. A borrower has a healthy position with `weighted_debts_value` just below `collateral_weighted_value`.
2. A small adverse price movement (e.g., 0.1% collateral price drop) causes `weighted_debts_value` to exceed `collateral_weighted_value` by a small epsilon, making the position eligible for liquidation.
3. A liquidation bot calls `liquidate()` at `liquidate.move:133` with `available_repay_coin` set to `close_factor * debt_balance` (the maximum allowed by the static cap, e.g., 50% of total debt).
4. `ensure_liquidate_borrow_allowed` at `market.move:722` passes because `repay_amount <= close_factor * debt_balance`.
5. `liquidate_calculate_seize_ctokens` at `market.move:750` computes seized collateral as `repay_amount * (1 + liquidation_incentive) * price_ratio / exchange_rate`.
6. The borrower loses ~50% of their debt value in collateral (plus the liquidation incentive premium), when only ~0.1% repayment would have been sufficient to restore health.

## Impact

The obligation holder suffers excessive collateral loss. For a position with $10,000 in debt that becomes unhealthy by $10 (0.1%):
- **Expected (soft liquidation):** ~$10-20 of debt repaid, ~$11-22 of collateral seized (enough to restore health).
- **Actual:** Up to $5,000 of debt repaid (50% close factor), ~$5,500 of collateral seized (including ~10% liquidation incentive).

This is a ~250x over-liquidation compared to the stated soft liquidation design. The liquidation bot profits from the excess seizure at the borrower's expense.

## PoC

Code inspection confirms the discrepancy:

1. Module header (`liquidate.move:2`): "Liquidation amount should be no bigger than the amount that would decrease the risk level of obligation to 1."
2. `ensure_liquidate_borrow_allowed` (`market.move:1008`): `max_debt_amount = debt_balance.mul(liquidation_params.close_factor)` — static percentage, not dynamic health-restoring calculation.
3. `handle_liquidation` (`market.move:506`): `close_factor` comes from `self.market_config().close_factor` — a fixed market parameter.
4. No computation exists anywhere in the liquidation path to calculate the minimum repay amount needed to restore `weighted_debts_value <= collateral_weighted_value`.

A dynamic cap would be:

```
R_max = (weighted_debts_value - collateral_weighted_value) / (debt_weight - collateral_weight * liquidation_incentive * price_ratio)
```

This formula ensures the position is restored to exactly the liquidation threshold after repayment and collateral seizure.

## Mitigation

Replace the static close factor cap with a dynamic calculation that limits liquidation to the minimum amount needed to restore the obligation to a healthy state:

1. After confirming the position is unhealthy (line 978-981), compute the exact repay amount `R_max` that would bring `weighted_debts_value` back to `collateral_weighted_value`.
2. Cap the allowed repay amount at `min(R_max, debt_balance)` instead of `debt_balance * close_factor`.
3. Retain the existing bad debt bypass (lines 984-992) for near-bad-debt positions where full liquidation is appropriate.
4. Retain the `close_factor_bypass_min_value` check (line 1006) for small positions where enforcement overhead isn't worthwhile.
