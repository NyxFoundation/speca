### Prolonged ADL activation will cause protocol insolvency as liquidation incentive grows unboundedly past 100%

### Summary

The ADL `liquidation_incentive` function computes `base + days * daily_penalty` with no upper cap, causing the incentive to grow linearly with time. During a prolonged ADL event (weeks), the incentive can exceed 100%, meaning liquidators receive more collateral value than the debt they repay, draining the protocol's reserves and causing insolvency for depositors.

### Root Cause

In [`adl.move:201-206`](contracts/protocol/sources/internal/market/adl.move#L201):

```move
public fun liquidation_incentive(self: &DeleverageParams, secs_since_activation: u64): Decimal {
    let days = secs_since_activation / SECONDS_IN_A_DAY;
    let add_on = self.liquidation_incentive_daily_penalty.mul_u64(days);
    self.liquidation_incentive_base.add(add_on)
}
```

There is no `min()` cap on the result. Compare with `liquidation_ltv` (line 208-212) which uses `saturating_sub` to prevent going below zero. The incentive has no analogous upper bound.

In `handle_debt_auto_deleverage` (market.move:589), the incentive is capped at the non-ADL maximum:
```move
liquidation_incentive: debt_params.liquidation_incentive(activation_time).min(max_liquidation_incentive),
```

However, `max_liquidation_incentive` comes from `collateral_setting.liquidation_incentive()` which is the eMode's configured incentive. If the eMode incentive is set high (e.g., 20%), and the daily penalty is 5%, after 20 days the ADL incentive reaches 100% + base. The `.min()` cap prevents exceeding the eMode setting, but eMode settings can be up to the protocol's maximum allowed (validated in `create_emode_params` line 93-96 of admin/emode.move).

The validation is: `liquidation_factor * (1 + incentive) < 1`. With `liquidation_factor = 0.95` and `incentive = 0.05`: `0.95 * 1.05 = 0.9975 < 1`. But with `liquidation_factor = 0.50` and `incentive = 0.90`: `0.50 * 1.90 = 0.95 < 1`. So a 90% incentive is valid.

If the ADL daily penalty reaches this 90% cap over days, liquidators seize 190% of debt value in collateral from borrowers.

### Internal Pre-conditions

1. Admin needs to activate ADL (Auto Deleverage) for an eMode group/asset
2. ADL needs to remain active for multiple days (no one resolves it by repaying enough)

### External Pre-conditions

1. Market conditions (e.g., sustained price decline) cause ADL to be activated and remain active for an extended period

### Attack Path

1. Market crash triggers ADL activation with `liquidation_incentive_base = 5%` and `daily_penalty = 5%`
2. ADL remains active for 10 days (insufficient repayment to resolve)
3. ADL incentive is now: `5% + 10 * 5% = 55%`
4. Liquidator calls `liquidate_adl_borrow` → seizes 155% of repaid debt value in collateral
5. Borrower loses 55% more collateral than the debt being repaid
6. After 18 days: incentive = 95%. Liquidator gets nearly 2x collateral per unit of debt repaid.

### Impact

Borrowers suffer excessive collateral loss during prolonged ADL events. The protocol effectively becomes insolvent as liquidators extract more value than they put in. Depositors bear the loss when the excess collateral seizure reduces the reserve's backing.

### PoC

```move
#[test_only]
module protocol::poc_065_adl_incentive_unbounded;

use protocol::adl;
use math::float;

const SECONDS_IN_A_DAY: u64 = 86400;

#[test]
fun test_adl_incentive_grows_unbounded() {
    let params = adl::new_auto_deleverage_params(
        1_000_000,                              // target_amount
        float::from_quotient(95, 100),          // liquidation_factor_base: 95%
        float::from_quotient(1, 100),           // liquidation_factor_hourly_drop: 1%/hr
        float::from_quotient(5, 100),           // liquidation_incentive_base: 5%
        float::from_quotient(5, 100),           // liquidation_incentive_daily_penalty: 5%/day
        float::from_quotient(50, 100),          // close_factor: 50%
    );

    // Day 0: incentive = 5%
    let inc_day0 = params.liquidation_incentive(0);
    assert!(inc_day0.eq(float::from_quotient(5, 100)), 0);

    // Day 10: incentive = 55%
    let inc_day10 = params.liquidation_incentive(10 * SECONDS_IN_A_DAY);
    assert!(inc_day10.eq(float::from_quotient(55, 100)), 1);

    // Day 20: incentive = 105% (!!)
    let inc_day20 = params.liquidation_incentive(20 * SECONDS_IN_A_DAY);
    assert!(inc_day20.gt(float::from_quotient(100, 100)), 2);
    // Liquidator gets MORE than 2x the debt value in collateral!

    // Day 50: incentive = 255%
    let inc_day50 = params.liquidation_incentive(50 * SECONDS_IN_A_DAY);
    assert!(inc_day50.gt(float::from_quotient(250, 100)), 3);
}
```

### Mitigation

Cap the ADL incentive at the eMode's configured maximum:

```move
public fun liquidation_incentive(self: &DeleverageParams, secs_since_activation: u64, max: Decimal): Decimal {
    let days = secs_since_activation / SECONDS_IN_A_DAY;
    let add_on = self.liquidation_incentive_daily_penalty.mul_u64(days);
    self.liquidation_incentive_base.add(add_on).min(max)
}
```

Or add a hard cap constant (e.g., 50%) in the function itself.
