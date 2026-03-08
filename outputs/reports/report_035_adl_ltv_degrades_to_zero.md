# ADL Liquidation LTV Degrades to Zero, Enabling Liquidation of All Positions

## Summary

The ADL (Auto-Deleverage) `liquidation_ltv` function uses `saturating_sub` without a minimum floor. After sufficient time, the LTV threshold reaches zero, making every position with any debt liquidatable regardless of collateralization ratio.

## Vulnerability Detail

In `adl.move:208-213`:

```move
public fun liquidation_ltv(self: &DeleverageParams, secs_since_activation: u64): Decimal {
    let hours = secs_since_activation / SECONDS_IN_AN_HOUR;

    let reduction = self.liquidation_factor_hourly_drop.mul_u64(hours);
    self.liquidation_factor_base.saturating_sub(reduction)
}
```

When `liquidation_factor_hourly_drop * hours >= liquidation_factor_base`, the `saturating_sub` returns `Decimal { value: 0 }` (zero).

This zero LTV is then used in `ensure_liquidate_borrow_allowed` (market.move:964-970):

```move
if (liquidation_params.liquidation_ltv_threshold_override.is_some()) {
    let liquidation_ltv = *liquidation_params.liquidation_ltv_threshold_override.borrow();
    let user_ltv = weighted_debts_value.div(collateral_total_value);
    assert!(
        user_ltv.gt(liquidation_ltv),  // user_ltv > 0 is ALWAYS true
        error::liquidation_obligation_still_safe(),
    );
```

When `liquidation_ltv = 0`, the check becomes `user_ltv > 0`, which passes for **any** obligation with non-zero debt, regardless of how well-collateralized it is.

## Internal Pre-conditions

1. ADL must be activated by admin for an eMode group.
2. Sufficient time must elapse such that `liquidation_factor_hourly_drop * hours >= liquidation_factor_base`.

## External Pre-conditions

1. Admin must fail to cancel ADL before the LTV threshold reaches zero (key compromise, unavailability, or oversight).

## Attack Path

1. Admin activates ADL with `liquidation_factor_base = 0.85` and `hourly_drop = 0.01`.
2. After 85 hours (~3.5 days), `saturating_sub` returns 0.
3. `ensure_liquidate_borrow_allowed` checks `user_ltv > 0`, which passes for any obligation with non-zero debt.
4. ADL liquidator can now liquidate perfectly healthy positions (e.g., 500% collateralized).
5. Collateral is seized from solvent borrowers.

## Impact

**Example scenario:**
- `liquidation_factor_base = 0.85` (85%)
- `liquidation_factor_hourly_drop = 0.01` (1% per hour)
- After 85 hours (~3.5 days): LTV threshold = 0

At this point, **every position in the eMode group with any debt is liquidatable** under ADL, including a position collateralized at 500% (LTV = 0.2). The ADL liquidator can seize collateral from perfectly healthy positions.

The `ensure_limit_breached` check (market.move:582) only verifies that the global total debt/deposit exceeds the target — it does NOT protect individual obligations from unfair liquidation when the per-obligation LTV threshold has degraded to zero.

While ADL is designed as an emergency mechanism with admin oversight, the lack of a minimum LTV floor creates catastrophic risk if:
1. Admin fails to cancel ADL promptly (key compromise, unavailability, oversight)
2. Admin intentionally or accidentally sets aggressive `hourly_drop` values
3. Network congestion delays the cancel transaction

## Code Snippet

- `adl.move:208-213` — `liquidation_ltv` with `saturating_sub` (no floor)
- `adl.move:201-206` — `liquidation_incentive` grows unboundedly (capped by `min` with emode incentive in market.move:589)
- `market.move:586-593` — ADL liquidation params construction
- `market.move:964-970` — LTV threshold check passes trivially when threshold = 0

## Tool used

Manual Review + Automated Analysis

## Mitigation

Add a minimum floor to `liquidation_ltv` to prevent degradation below a safe threshold:

```move
const MIN_LIQUIDATION_LTV: u64 = 1; // 0.01% minimum floor

public fun liquidation_ltv(self: &DeleverageParams, secs_since_activation: u64): Decimal {
    let hours = secs_since_activation / SECONDS_IN_AN_HOUR;
    let reduction = self.liquidation_factor_hourly_drop.mul_u64(hours);
    let ltv = self.liquidation_factor_base.saturating_sub(reduction);

    // Enforce minimum floor to prevent liquidation of healthy positions
    let min_ltv = float::from_percent(MIN_LIQUIDATION_LTV);
    if (ltv.lt(min_ltv)) { min_ltv } else { ltv }
}
```

Additionally, consider adding a maximum activation duration in the admin entry point (`adl_admin.move`) that caps how long ADL can remain active before auto-cancellation.
