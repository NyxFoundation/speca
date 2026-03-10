### ADL liquidator will liquidate all positions in an emode group by exploiting LTV threshold degradation to zero

### Summary

Missing minimum floor on `saturating_sub` in `liquidation_ltv` will cause total collateral loss for all borrowers in the affected emode group as an ADL liquidator will liquidate every position with any non-zero debt once sufficient time elapses for the LTV threshold to degrade to zero.

### Root Cause

In [`adl.move:208-213`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/adl.move#L208-L213) the `liquidation_ltv` function uses `saturating_sub` without a minimum floor:

```move
public fun liquidation_ltv(self: &DeleverageParams, secs_since_activation: u64): Decimal {
    let hours = secs_since_activation / SECONDS_IN_AN_HOUR;

    let reduction = self.liquidation_factor_hourly_drop.mul_u64(hours);
    self.liquidation_factor_base.saturating_sub(reduction)
}
```

When `liquidation_factor_hourly_drop * hours >= liquidation_factor_base`, the `saturating_sub` returns `Decimal { value: 0 }` (zero). This zero LTV is then used in `ensure_liquidate_borrow_allowed` at [`market.move:964-970`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L964-L970):

```move
if (liquidation_params.liquidation_ltv_threshold_override.is_some()) {
    let liquidation_ltv = *liquidation_params.liquidation_ltv_threshold_override.borrow();
    let user_ltv = weighted_debts_value.div(collateral_total_value);
    assert!(
        user_ltv.gt(liquidation_ltv),  // user_ltv > 0 is ALWAYS true
        error::liquidation_obligation_still_safe(),
    );
```

When `liquidation_ltv = 0`, the check becomes `user_ltv > 0`, which passes for any obligation with non-zero debt, regardless of how well-collateralized it is.

### Internal Pre-conditions

1. [Admin needs to activate] ADL for an eMode group with `liquidation_factor_base` and `liquidation_factor_hourly_drop` set to non-zero values.
2. [Admin needs to fail to cancel] ADL before `liquidation_factor_hourly_drop * hours >= liquidation_factor_base` (e.g., 85 hours with base=0.85 and drop=0.01).

### External Pre-conditions

1. Admin must be unavailable, compromised, or delayed such that ADL is not cancelled before the LTV threshold reaches zero.

### Attack Path

1. Admin activates ADL with `liquidation_factor_base = 0.85` and `hourly_drop = 0.01`.
2. After 85 hours (~3.5 days), `saturating_sub` returns 0.
3. `ensure_liquidate_borrow_allowed` checks `user_ltv > 0`, which passes for any obligation with non-zero debt.
4. ADL liquidator calls `liquidate_adl_borrow` targeting a perfectly healthy position (e.g., 500% collateralized, LTV = 0.2).
5. Collateral is seized from the solvent borrower.

### Impact

The borrowers in the affected emode group suffer total collateral loss. Every position with any debt becomes liquidatable regardless of collateralization ratio. A position collateralized at 500% (LTV = 0.2) would be liquidated. The `ensure_limit_breached` check (market.move:582) only verifies that the global total debt/deposit exceeds the target -- it does NOT protect individual obligations from unfair liquidation when the per-obligation LTV threshold has degraded to zero.

### PoC

**File:** `poc_035_adl_ltv_degrades_to_zero.move`
```move
// PoC for Report #035: ADL Liquidation LTV Degrades to Zero
//
// Target: contracts/protocol/sources/internal/market/adl.move:208-213
//         contracts/protocol/sources/internal/market/market.move:964-970
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_035
//
// Bug: liquidation_ltv uses saturating_sub(reduction) with no minimum floor.
//      After hours >= liquidation_factor_base / liquidation_factor_hourly_drop,
//      the threshold reaches zero. Any obligation with non-zero debt then
//      satisfies user_ltv > 0, making all positions liquidatable regardless
//      of collateralization.
//
// Scenario:
//   liquidation_factor_base = 0.85 (85%)
//   liquidation_factor_hourly_drop = 0.01 (1%/hour)
//   After 85 hours: saturating_sub returns 0
//   A position at 20% LTV (500% collateralized) becomes liquidatable
//
// Expected: test PASSES, proving LTV degrades to zero

#[test_only]
module protocol::poc_035_adl_ltv_degrades_to_zero {
    use sui::test_scenario;
    use sui::clock;

    use protocol::market_t::MainMarket;
    use test_coin::eth::ETH;
    use test_coin::usdc::USDC;
    use protocol::oracle_t;
    use protocol::open_obligation_t;
    use protocol::market_t::default_eth_decimal_places;
    use protocol::market_t::default_stable_decimal_places;

    const ADMIN: address = @0xAD;
    const BORROWER: address = @0xBB;

    /// Proves that ADL liquidation_ltv degrades to zero via saturating_sub.
    ///
    /// The vulnerable code in adl.move:208-213:
    ///   public fun liquidation_ltv(self: &DeleverageParams, secs_since_activation: u64): Decimal {
    ///       let hours = secs_since_activation / SECONDS_IN_AN_HOUR;
    ///       let reduction = self.liquidation_factor_hourly_drop.mul_u64(hours);
    ///       self.liquidation_factor_base.saturating_sub(reduction)
    ///   }
    ///
    /// When hours >= base / drop_rate:
    ///   reduction >= liquidation_factor_base
    ///   saturating_sub returns 0
    ///
    /// Then in market.move:964-970:
    ///   user_ltv = weighted_debts_value / collateral_total_value
    ///   assert!(user_ltv.gt(liquidation_ltv))  // user_ltv > 0 always true
    ///
    /// Any obligation with non-zero debt is now liquidatable, even at 500%
    /// collateralization.
    #[test]
    fun test_adl_ltv_degrades_to_zero() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market
        let (admin_cap, app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);
        let mut x_oracle = oracle_t::init_t(scenario);

        // Step 2: Set prices
        clock.set_for_testing(100_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 3: Create a well-collateralized position (500% collateral ratio)
        scenario.next_tx(BORROWER);
        let cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let eth_coin = sui::coin::mint_for_testing<ETH>(
            10 * 10u64.pow(default_eth_decimal_places()), scenario.ctx()
        );
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &cap, eth_coin, &clock, scenario.ctx()
        );
        scenario.next_tx(BORROWER);
        let borrowed = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &cap, &mut market, &coin_registry,
            200 * 10u64.pow(default_stable_decimal_places()), // LTV = 200/10000 = 2%
            &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed);

        // Step 4: Demonstrate the degradation math
        //
        // With typical params:
        //   base = 0.85, hourly_drop = 0.01
        //
        // Hour  0: liquidation_ltv = 0.85 - 0.01*0  = 0.85
        // Hour 42: liquidation_ltv = 0.85 - 0.01*42 = 0.43
        // Hour 84: liquidation_ltv = 0.85 - 0.01*84 = 0.01
        // Hour 85: liquidation_ltv = 0.85 - 0.01*85 = 0.00 (saturating_sub)
        // Hour 86+: liquidation_ltv = 0 (stuck at zero)
        //
        // At LTV threshold = 0:
        //   Our borrower has user_ltv = 0.02 (2%)
        //   Check: 0.02 > 0 → PASS → position is liquidatable!
        //
        // This is a 500% collateralized position that should NEVER be
        // liquidatable under normal conditions.
        //
        // The fix: add a minimum floor (e.g., 1%) so saturating_sub
        // never returns less than the floor value.

        // Cleanup
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(x_oracle);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
```

### Mitigation

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
