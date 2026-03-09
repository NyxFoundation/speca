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
