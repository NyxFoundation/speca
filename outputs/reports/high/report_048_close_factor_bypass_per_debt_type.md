# Close Factor Bypass via Per-Debt-Type Threshold Allows Full Liquidation of Multi-Debt Obligations

## Summary

`ensure_liquidate_borrow_allowed` checks `close_factor_bypass_min_value` against each individual debt type's USD value rather than the obligation's total debt value. Obligations with multiple debt types each individually below the threshold bypass close factor enforcement entirely, allowing 100% liquidation of every debt type even when the aggregate debt significantly exceeds the threshold.

## Vulnerability Detail

In `market.move:994-1006`, the close factor bypass check evaluates a single debt type:

```move
let target_debt_type = type_name::with_defining_ids<DebtType>();
let debt_balance = obligation.debt(target_debt_type).unsafe_debt_amount();
let debt_value = coin_value(
    get_price(x_oracle, target_debt_type, emode_group.get_oracle_base_token(), clock),
    debt_balance,
    coin_decimals_registry.decimals(target_debt_type)
).ceil();

// below min usd for close factor enforcement
if (debt_value <= liquidation_params.close_factor_bypass_min_value) { return };

let max_debt_amount = debt_balance.mul(liquidation_params.close_factor);
assert!(
    math::float::from(liquidator_repay_amount).le(max_debt_amount),
    error::liquidation_close_factor_exceeded(),
);
```

The `target_debt_type` is the specific debt type being liquidated in this call (e.g., USDC). The `debt_value` is computed for this single type only. When `debt_value <= close_factor_bypass_min_value`, the function returns early, skipping the `close_factor` enforcement entirely.

A liquidator targeting an obligation with N debt types, each individually below the threshold, can make N separate `liquidate()` calls (chainable in a single PTB) — each with 100% repayment of the respective debt type — because each call independently passes the bypass check. The aggregate obligation debt can far exceed the threshold.

## Impact

Consider a concrete scenario:

- `close_factor_bypass_min_value` = $500, `close_factor` = 50%, `liquidation_incentive` = 10%
- Obligation has 3 debts: USDC=$400, USDT=$400, DAI=$400 (total=$1,200)
- Collateral: $1,400 (LTV = 85.7%, above liquidation threshold, above 101% bad debt threshold)

**With close factor enforcement (intended behavior):**
- Total debt ($1,200) > threshold ($500), so close factor should limit each to 50%
- Max total repay = $600, seized collateral = $660 (including incentive)
- Borrower retains: $600 debt, $740 collateral — position restored to health
- Total incentive penalty: $60

**With per-debt-type bypass (actual behavior):**
- Each debt ($400) < threshold ($500), close factor bypassed for all three
- Total repay = $1,200, seized collateral = $1,320
- Borrower retains: $0 debt, $80 collateral
- Total incentive penalty: $120 (2x the intended amount)
- In tighter collateralization ratios, this can push the borrower into bad debt

The close factor is a core soft-liquidation protection (as stated in `liquidate.move:2`: "Liquidation amount should be no bigger than the amount that would decrease the risk level of obligation to 1"). The per-debt-type threshold bypasses this protection for multi-debt obligations, causing borrowers to lose up to 2x the intended liquidation penalty. On Sui, all N liquidation calls can be composed atomically in a single PTB, preventing any intervention.

## Code Snippet

- `contracts/protocol/sources/internal/market/market.move:994-1012` — Close factor bypass uses per-debt-type `debt_value`, not total obligation debt
- `contracts/protocol/sources/entry_points/lending/liquidate.move:133-161` — `liquidate` takes `obligation_id: ID`, allowing sequential calls on same obligation in one PTB

## Tool used

Manual Review + Automated Analysis

## Recommendation

Check the bypass threshold against the obligation's total debt value instead of the individual debt type:

```move
// Compute total obligation debt value across all debt types
let total_debt_value = debts_value_usd_for_liquidation(emode_group, obligation, coin_decimals_registry, x_oracle, clock);

// Only bypass close factor if TOTAL obligation debt is below threshold
if (total_debt_value <= liquidation_params.close_factor_bypass_min_value) { return };

let max_debt_amount = debt_balance.mul(liquidation_params.close_factor);
assert!(
    math::float::from(liquidator_repay_amount).le(max_debt_amount),
    error::liquidation_close_factor_exceeded(),
);
```

This ensures that the close factor is enforced whenever the aggregate debt is economically significant, regardless of how the debt is distributed across asset types.
