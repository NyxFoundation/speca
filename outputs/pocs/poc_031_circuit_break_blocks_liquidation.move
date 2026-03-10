// PoC for Report #031: Circuit Break Blocks Liquidation
//
// Target: contracts/protocol/sources/entry_points/lending/liquidate.move:59
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_031
//
// Bug: pre_liquidation_check unconditionally asserts that circuit breaker
//      has not been triggered. All three liquidation paths (normal, ADL borrow,
//      ADL collateral) are gated behind this check, preventing any liquidation
//      during a circuit break — the exact scenario where liquidation is most
//      needed (market stress).
//
// Scenario:
//   1. Admin triggers circuit breaker during market stress
//   2. Collateral prices continue dropping
//   3. Underwater positions cannot be liquidated
//   4. Bad debt accumulates during the entire circuit break period
//
// Expected: test PASSES (liquidation blocked during circuit break)

#[test_only]
module protocol::poc_031_circuit_break_blocks_liquidation {
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
    const LIQUIDATOR: address = @0xCC;

    /// Proves that liquidation is blocked during circuit break,
    /// even when positions are underwater and need immediate liquidation.
    ///
    /// The circuit breaker at liquidate.move:59 blocks ALL liquidation paths:
    ///   assert!(!market.has_circuit_break_triggered(),
    ///           protocol::error::market_under_circuit_break());
    ///
    /// This is called by pre_liquidation_check which gates:
    ///   - liquidate / liquidate_as_coin (line 177)
    ///   - liquidate_adl_borrow (line 224)
    ///   - liquidate_adl_deposit (line 273)
    #[test]
    #[expected_failure(abort_code = protocol::error::market_under_circuit_break)]
    fun test_circuit_break_blocks_liquidation() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market
        let (admin_cap, mut app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);
        let mut x_oracle = oracle_t::init_t(scenario);

        // Step 2: Set prices
        clock.set_for_testing(100_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 3: Borrower creates underwater position
        scenario.next_tx(BORROWER);
        let borrower_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let eth_coin = sui::coin::mint_for_testing<ETH>(
            1 * 10u64.pow(default_eth_decimal_places()), scenario.ctx()
        );
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &borrower_cap, eth_coin, &clock, scenario.ctx()
        );
        scenario.next_tx(BORROWER);
        let borrowed = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &borrower_cap, &mut market, &coin_registry,
            500 * 10u64.pow(default_stable_decimal_places()),
            &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed);

        // Step 4: Drop price to make position liquidatable
        clock.set_for_testing(101_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(500, 0));

        // Step 5: Admin triggers circuit breaker
        scenario.next_tx(ADMIN);
        protocol::market_admin::trigger_circuit_break<MainMarket>(
            &admin_cap, &app, &mut market
        );

        // Step 6: Setup liquidation permission
        scenario.next_tx(LIQUIDATOR);
        let permit = protocol::whitelist_admin::mint_new_whitelist(
            &admin_cap, &mut app, scenario.ctx()
        );
        protocol::whitelist_admin::update_permission(
            &admin_cap, &mut app, object::id(&permit),
            protocol::whitelist_admin::liquidation(), true
        );

        // Step 7: Attempt liquidation — should FAIL with circuit_break error
        // This proves the bug: positions are underwater but cannot be liquidated
        let usdc_repay = sui::coin::mint_for_testing<USDC>(
            300 * 10u64.pow(default_stable_decimal_places()), scenario.ctx()
        );
        let (seized, refund) =
            protocol::liquidate::liquidate_as_coin<MainMarket, USDC, ETH>(
                &app, &permit, borrower_cap.id(), &mut market,
                usdc_repay, &coin_registry, &x_oracle, &clock, scenario.ctx()
            );

        // Should not reach here — circuit break blocks liquidation
        std::unit_test::destroy(seized);
        std::unit_test::destroy(refund);
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(borrower_cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(permit);
        std::unit_test::destroy(x_oracle);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
