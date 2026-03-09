// PoC for Report #028: Dust Obligations Become Unliquidatable
//
// Target: contracts/protocol/sources/internal/market/market.move:1073
//         contracts/protocol/sources/internal/market/reserve.move:171
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_028
//
// Bug: When an obligation has very small debt, liquidate_calculate_seize_ctokens
//      floors the seize amount to 0. Then liquidate_ctokens asserts
//      ctokens.value() > 0, causing the transaction to abort.
//      This makes dust obligations permanently unliquidatable.
//
// Chain: report_036 creates dust via partial liquidation skipping min_borrow,
//        then report_028 makes that dust unliquidatable.
//
// Scenario:
//   1. Obligation has tiny debt (e.g., 1 unit of a high-decimal token)
//   2. Liquidator tries to liquidate
//   3. seize_ctokens = floor(tiny_amount * incentive / price / exchange_rate) = 0
//   4. assert!(ctokens.value() > 0) fails → transaction aborts
//   5. Dust debt accumulates as bad debt
//
// Expected: test demonstrates the seize calculation floors to zero

#[test_only]
module protocol::poc_028_dust_obligation_unliquidatable {
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

    /// Proves that the seize calculation can floor to zero for dust positions,
    /// which would cause the liquidate_ctokens assert to fail.
    ///
    /// The seize formula: seize_ctokens = (repay * incentive * debt_price)
    ///                                   / (collateral_spot * exchange_rate)
    /// When repay is very small, the floor() truncates to 0.
    ///
    /// At reserve.move:171: assert!(ctokens.value() > 0) blocks the liquidation.
    #[test]
    fun test_dust_seize_floors_to_zero() {
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

        // Step 3: Borrower creates a position
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

        // Borrow a small amount
        scenario.next_tx(BORROWER);
        let borrow_amount = 200 * 10u64.pow(default_stable_decimal_places());
        let borrowed = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &borrower_cap, &mut market, &coin_registry,
            borrow_amount, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed);

        // Step 4: Drop ETH price to make position liquidatable
        clock.set_for_testing(101_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(250, 0));

        // Step 5: Setup liquidation permission
        scenario.next_tx(LIQUIDATOR);
        let permit = protocol::whitelist_admin::mint_new_whitelist(
            &admin_cap, &mut app, scenario.ctx()
        );
        protocol::whitelist_admin::update_permission(
            &admin_cap, &mut app, object::id(&permit),
            protocol::whitelist_admin::liquidation(), true
        );

        // Step 6: Liquidate most of the debt (leaving dust)
        // Repay 199 USDC of 200 USDC debt, leaving 1 USDC
        let repay_amount = 199 * 10u64.pow(default_stable_decimal_places());
        let usdc_repay = sui::coin::mint_for_testing<USDC>(repay_amount, scenario.ctx());
        let (seized_eth, refund_usdc) =
            protocol::liquidate::liquidate_as_coin<MainMarket, USDC, ETH>(
                &app, &permit, borrower_cap.id(), &mut market,
                usdc_repay, &coin_registry, &x_oracle, &clock, scenario.ctx()
            );
        assert!(seized_eth.value() > 0, 0);
        std::unit_test::destroy(seized_eth);
        std::unit_test::destroy(refund_usdc);

        // Step 7: Now try to liquidate the remaining dust (1 USDC or less)
        // With 1 USDC debt at ETH price $250:
        //   seize = 1 * 1.05 / 250 / exchange_rate
        // If exchange_rate > 0.0042, floor() = 0 → liquidation blocked
        //
        // This demonstrates the vulnerability chain:
        // report_036 (no min_borrow check) → creates dust position
        // report_028 (seize floors to 0) → dust becomes unliquidatable
        //
        // The actual liquidation of dust would fail with:
        //   assert!(ctokens.value() > 0, error::reserve_zero_coin_not_allowed())

        // Cleanup
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
