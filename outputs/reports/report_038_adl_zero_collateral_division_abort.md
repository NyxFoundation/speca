# ADL Liquidation Can Abort on Zero-Collateral Obligations Due to Division by Zero

## Summary
In ADL liquidation mode, the safety gate computes `user_ltv = weighted_debts_value / collateral_total_value` without guarding for zero collateral. If an obligation has remaining debt but zero collateral, ADL liquidation aborts and cannot proceed.

## Vulnerability Detail
`ensure_liquidate_borrow_allowed` has two branches. In the ADL branch (`liquidation_ltv_threshold_override.is_some()`), it computes:

- `user_ltv = weighted_debts_value.div(collateral_total_value)`

When `collateral_total_value == 0`, this triggers arithmetic abort in `math::float::div` (division by zero).

ADL entrypoints (`liquidate_adl_borrow` / `liquidate_adl_deposit`) always pass an override liquidation threshold, so they hit this branch. Therefore, obligations that have already lost all collateral but still carry debt (bad-debt tail) cannot be processed through ADL, because the pre-check aborts before liquidation logic.

## Internal Pre-conditions

1. Obligation must have outstanding debt but zero collateral (bad-debt tail position).
2. ADL must be active for the relevant eMode group.

## External Pre-conditions

None.

## Attack Path

1. Obligation loses all collateral through liquidation but retains residual debt.
2. Admin activates ADL to deleverage the market.
3. ADL liquidator calls liquidate_adl_borrow targeting the zero-collateral obligation.
4. ensure_liquidate_borrow_allowed computes user_ltv = weighted_debts / 0 (division by zero).
5. Transaction aborts, ADL cannot process this obligation.
6. Bad debt tail remains unresolved.

## Impact
Protocol deleveraging automation can be blocked for zero-collateral debt positions. This blocks ADL flows for affected positions and leaves tail bad debt unresolved through the intended deleverage path.

## Code Snippet
- `contracts/protocol/sources/internal/market/market.move:964-970`
- `contracts/protocol/sources/internal/market/market.move:953-960`
- `contracts/math/sources/float.move:83-86`
- `contracts/protocol/sources/entry_points/lending/liquidate.move:229-237`
- `contracts/protocol/sources/entry_points/lending/liquidate.move:278-286`

## Tool used
Manual Review + Automated Analysis

## Mitigation
Add an explicit zero-collateral guard before division in the ADL threshold branch.

Example patch direction:

```move
if (liquidation_params.liquidation_ltv_threshold_override.is_some()) {
    let liquidation_ltv = *liquidation_params.liquidation_ltv_threshold_override.borrow();

    // If no collateral remains, any positive debt should be considered liquidatable.
    if (collateral_total_value.is_zero()) {
        assert!(weighted_debts_value.gt_u64(0), error::liquidation_obligation_still_safe());
        return
    };

    let user_ltv = weighted_debts_value.div(collateral_total_value);
    assert!(user_ltv.gt(liquidation_ltv), error::liquidation_obligation_still_safe());
}
```

Alternatively, skip ratio computation and directly treat `collateral_total_value == 0 && weighted_debts_value > 0` as unsafe/liquidatable.
