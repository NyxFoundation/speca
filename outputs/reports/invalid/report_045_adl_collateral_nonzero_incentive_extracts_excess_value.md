# ADL Collateral Deleverage Extracts Excess Value from Obligation Holders via Non-Zero Liquidation Incentive

## Summary

`handle_collateral_auto_deleverage` passes a non-zero and time-increasing `liquidation_incentive` to `liquidation_inner`, causing the ADL operator to seize collateral worth more than the debt repaid. Obligation holders — who may be perfectly healthy — lose excess collateral proportional to the incentive rate, which grows daily.

## Root Cause

In [`market.move:654-661`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L654-L661), `handle_collateral_auto_deleverage` constructs `LiquidationParams` with a non-zero incentive:

```move
let liquidation_params = LiquidationParams {
    liquidation_ltv_threshold_override: std::option::some(collateral_params.liquidation_ltv(activation_time)),
    // adl liquidation_incentive should not have exceeded non-adl liquidation_incentive
    liquidation_incentive: collateral_params.liquidation_incentive(activation_time).min(max_liquidation_incentive),
    liquidation_revenue_factor: float::zero(),
    close_factor: collateral_params.close_factor(),
    close_factor_bypass_min_value,
};
```

The incentive is computed in [`adl.move:201-206`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/adl.move#L201-L206):

```move
public fun liquidation_incentive(self: &DeleverageParams, secs_since_activation: u64): Decimal {
    let days = secs_since_activation / SECONDS_IN_A_DAY;
    let add_on = self.liquidation_incentive_daily_penalty.mul_u64(days);
    self.liquidation_incentive_base.add(add_on)
}
```

This is `liquidation_incentive_base + (daily_penalty × days_elapsed)`, a value that starts non-zero and grows daily. The incentive feeds into `liquidate_calculate_seize_ctokens` at [`market.move:1058-1060`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L1058-L1060):

```move
let incentivised_borrow = actual_repay_amount.add(actual_repay_amount.mul(liquidation_incentive));
```

The seized collateral value = `repay_amount × (1 + incentive)`, exceeding the debt repaid. Additionally, `liquidation_revenue_factor` is set to `float::zero()` (line 658), so no protocol fee is taken — the entire excess goes to the ADL operator.

## Internal Pre-conditions

1. Total deposits of a collateral type must exceed the ADL collateral deleverage limit configured in `AutoDeleverageRegistry`.
2. The ADL collateral deleverage timelock for the asset must be activated (non-zero `activation_time`).
3. Admin must have configured `DeleverageParams` with non-zero `liquidation_incentive_base` (the default admin function `new_adl_params` accepts this as a parameter).

## External Pre-conditions

None. The ADL operator (a whitelisted `PackageCallerCap` holder) triggers the deleverage unilaterally.

## Attack Path

1. Market conditions cause total deposits of collateral type X to exceed the ADL limit. The timelock activates.
2. Days pass, increasing the `liquidation_incentive` via the daily penalty formula (e.g., base=2% + 1%/day → 5% after 3 days).
3. ADL operator calls `liquidate_adl_deposit<MarketType, DebtType, CollateralType>()` targeting an obligation that has both debt and collateral X.
4. `handle_collateral_auto_deleverage` computes `liquidation_incentive = 5%`, `liquidation_revenue_factor = 0`.
5. `liquidation_inner` calculates `seized_collateral_value = repay_amount × 1.05`.
6. For 1000 USDC of debt repaid, the obligation holder loses 1050 USDC worth of collateral.
7. The ADL operator receives the full 1050 USDC in collateral (no protocol fee deducted).
8. The obligation holder — whose position may be perfectly healthy — loses 50 USDC of excess collateral beyond the debt covered.

The daily penalty creates a perverse incentive: ADL operators are motivated to delay deleverage to maximize their extraction. Each day of delay increases the incentive, penalizing obligation holders further while rewarding operator inaction.

## Impact

Obligation holders forcibly deleveraged lose collateral worth `repay_amount × liquidation_incentive` beyond the debt repaid. With typical parameters (base 2-5%, daily penalty 0.5-1%), the loss scales to 5-15% excess extraction after several days of timelock activation.

This is distinct from report_001 (ADL Borrow seizing collateral it shouldn't) because:
- Report_001 covers ADL **Borrow** path where collateral should NOT be seized at all
- This finding covers ADL **Collateral** path where collateral IS legitimately seized but the incentive creates excess extraction beyond bad debt coverage

The protocol design intent for ADL is to reduce systemic risk at minimal cost to obligation holders. A non-zero incentive contradicts this by penalizing healthy obligation holders to benefit the ADL operator.

## PoC

Code inspection confirms the vulnerability:

1. `handle_collateral_auto_deleverage` (`market.move:654-661`): `liquidation_incentive` is set to `collateral_params.liquidation_incentive(activation_time)` — non-zero and time-increasing.
2. `DeleverageParams.liquidation_incentive` (`adl.move:201-206`): returns `base + daily_penalty × days` — guaranteed non-zero if `liquidation_incentive_base > 0`.
3. `liquidate_calculate_seize_ctokens` (`market.move:1058-1060`): `incentivised_borrow = repay_amount × (1 + incentive)` — seized value exceeds repaid debt.
4. `liquidation_revenue_factor = float::zero()` (line 658) — no protocol fee, operator keeps full excess.
5. Entry point `liquidate_adl_deposit` (`liquidate.move:259-304`): transfers seized collateral to `ctx.sender()` (the ADL operator) at line 303.

## Mitigation

For ADL collateral deleverage, the liquidation incentive should be zero to ensure seized value equals exactly the bad debt covered:

```move
let liquidation_params = LiquidationParams {
    liquidation_ltv_threshold_override: std::option::some(collateral_params.liquidation_ltv(activation_time)),
    liquidation_incentive: float::zero(),  // No excess extraction in ADL
    liquidation_revenue_factor: float::zero(),
    close_factor: collateral_params.close_factor(),
    close_factor_bypass_min_value,
};
```

If an incentive is desired to attract ADL operators, it should be funded by the protocol treasury (e.g., from accumulated `cash_reserve`) rather than extracted from the obligation holder's collateral.
