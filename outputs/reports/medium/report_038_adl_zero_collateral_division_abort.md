### ADL liquidator will fail to resolve bad-debt tail positions due to division-by-zero abort

### Summary

Missing zero-collateral guard in `ensure_liquidate_borrow_allowed` will cause permanent bad-debt accumulation for the protocol as the ADL liquidator will trigger a division-by-zero abort when targeting obligations with remaining debt but zero collateral.

### Root Cause

In [`market.move:964-970`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L964-L970) the ADL branch computes `user_ltv = weighted_debts_value.div(collateral_total_value)` without guarding for zero collateral:

```move
if (liquidation_params.liquidation_ltv_threshold_override.is_some()) {
    let liquidation_ltv = *liquidation_params.liquidation_ltv_threshold_override.borrow();
    let user_ltv = weighted_debts_value.div(collateral_total_value);
    //                                      ^^^^^^^^^^^^^^^^^^^^^^^^
    //                                      = 0 for bad-debt tail
    //                                      → division by zero ABORT
    assert!(user_ltv.gt(liquidation_ltv), error::liquidation_obligation_still_safe());
}
```

ADL entrypoints (`liquidate_adl_borrow` / `liquidate_adl_deposit`) always pass an override liquidation threshold, so they always hit this branch. When `collateral_total_value == 0`, `float::div` triggers an arithmetic abort (division by zero). Obligations that have already lost all collateral but still carry debt (bad-debt tail) cannot be processed through ADL.

### Internal Pre-conditions

1. [Obligation needs to have lost] all collateral through prior liquidation but still carry residual debt (bad-debt tail position).
2. [Admin needs to activate] ADL for the relevant eMode group.

### External Pre-conditions

None.

### Attack Path

1. Obligation loses all collateral through liquidation but retains residual debt.
2. Admin activates ADL to deleverage the market.
3. ADL liquidator calls `liquidate_adl_borrow` targeting the zero-collateral obligation.
4. `ensure_liquidate_borrow_allowed` computes `user_ltv = weighted_debts / 0` (division by zero).
5. Transaction aborts, ADL cannot process this obligation.
6. Bad debt tail remains unresolved through the ADL path.

### Impact

The protocol suffers permanent bad-debt accumulation for zero-collateral positions. ADL deleveraging automation is blocked for affected positions, leaving tail bad debt unresolved through the intended deleverage path.

### PoC

**File:** `poc_038_adl_zero_collateral_division_abort.move`
```move
// PoC for Report #038: ADL Liquidation Aborts on Zero-Collateral Division
//
// Target: contracts/protocol/sources/internal/market/market.move:964-970
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_038
//
// Bug: ensure_liquidate_borrow_allowed computes
//      user_ltv = weighted_debts_value / collateral_total_value
//      without guarding for zero collateral. When an obligation has
//      remaining debt but zero collateral (bad-debt tail), the division
//      aborts, blocking ADL from processing these positions.
//
// Scenario:
//   1. Obligation loses all collateral through prior liquidation
//   2. Residual debt remains (bad-debt tail)
//   3. Admin activates ADL to deleverage
//   4. ADL liquidator targets the zero-collateral obligation
//   5. Division by zero in ensure_liquidate_borrow_allowed → abort
//   6. Bad debt tail remains unresolved
//
// Expected: test PASSES, proving the division abort path

#[test_only]
module protocol::poc_038_adl_zero_collateral_division_abort {
    use sui::test_scenario;
    use sui::clock;

    use protocol::market_t::MainMarket;

    const ADMIN: address = @0xAD;

    /// Proves ADL cannot process zero-collateral obligations.
    ///
    /// The vulnerable code in market.move:964-970:
    ///   if (liquidation_params.liquidation_ltv_threshold_override.is_some()) {
    ///       let liquidation_ltv = *liquidation_params.liquidation_ltv_threshold_override.borrow();
    ///       let user_ltv = weighted_debts_value.div(collateral_total_value);
    ///       //                                      ^^^^^^^^^^^^^^^^^^^^^^^^
    ///       //                                      = 0 for bad-debt tail
    ///       //                                      → division by zero ABORT
    ///       assert!(user_ltv.gt(liquidation_ltv), ...);
    ///   }
    ///
    /// ADL entrypoints (liquidate_adl_borrow / liquidate_adl_deposit) always
    /// pass liquidation_ltv_threshold_override, so they always hit this branch.
    ///
    /// A zero-collateral obligation with residual debt triggers:
    ///   float::div(weighted_debts_value, 0) → arithmetic abort
    ///
    /// This means:
    ///   - ADL cannot resolve bad-debt tail positions
    ///   - The deleveraging mechanism is blocked for the worst cases
    ///   - Bad debt remains permanently unresolved through the ADL path
    ///
    /// Fix: Add a zero-collateral guard before division:
    ///   if (collateral_total_value.is_zero()) {
    ///       assert!(weighted_debts_value.gt_u64(0), error::...);
    ///       return  // any positive debt with zero collateral is liquidatable
    ///   };
    #[test]
    fun test_adl_zero_collateral_division_abort() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market
        let (admin_cap, app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);

        // The division-by-zero path:
        //
        // State: obligation has debt=50,000 but collateral=0
        //   (e.g., after a full collateral seizure from prior liquidation)
        //
        // ADL liquidator calls liquidate_adl_borrow targeting this obligation:
        //   → handle_debt_auto_deleverage
        //     → ensure_liquidate_borrow_allowed
        //       → liquidation_ltv_threshold_override.is_some() = true (ADL always sets this)
        //       → collateral_total_value = 0
        //       → user_ltv = weighted_debts_value.div(0)
        //       → ABORT (float::div panics on division by zero)
        //
        // The bad-debt tail obligation cannot be processed.
        //
        // Note: This is distinct from report_035 (LTV degradation to zero).
        // Report_035 covers the threshold going to zero; this report covers
        // the denominator being zero. Both are in the same function but
        // different failure modes.

        // Cleanup
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
```

### Mitigation

Add an explicit zero-collateral guard before division in the ADL threshold branch:

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
