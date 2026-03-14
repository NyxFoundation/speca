// PoC for Report #028: Dust Obligations Become Unliquidatable
//
// Target: contracts/protocol/sources/internal/market/market.move:1073
//         contracts/protocol/sources/internal/market/reserve.move:171
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_028
//
// Bug: When repay amount is small enough, liquidate_calculate_seize_ctokens
//      returns floor(seize) = 0, and liquidate_ctokens asserts
//      ctokens.value() > 0, causing the transaction to abort.
//
// Math:
//   seize_ctokens = repay * (1 + incentive) * price_debt / debt_decimals
//                   / price_collateral * collateral_decimals / exchange_rate
//
//   With USDC debt (6 dec), ETH collateral (8 dec, $250):
//   seize = 1 * 1.05 * $1 / 10^6 / $250 * 10^8 / 1.0
//         = 1.05 * 100 / (250 * 10^6) ≈ 0.00000042
//   floor(0.00000042) = 0 → liquidation aborts!
//
// This means ANY dust position with ≤2 raw USDC units of debt
// becomes permanently unliquidatable, accumulating bad debt.
// report_036 creates these dust positions via missing min_borrow check.
//
// Expected: test PASSES via #[expected_failure]

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

    /// Proves that a small-enough repay causes seize_ctokens.floor() = 0,
    /// which aborts the liquidation via assert!(ctokens.value() > 0).
    ///
    /// This demonstrates the terminal step: once a dust position exists
    /// (created via report_036's missing min_borrow check), it cannot
    /// be liquidated and becomes permanent bad debt.
    #[test]
    #[expected_failure]
    fun test_dust_liquidation_aborts_on_zero_seize() {
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

        // Step 3: Borrower deposits 1 ETH ($1000), borrows 500 USDC
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
        let borrow_amount = 500 * 10u64.pow(default_stable_decimal_places());
        let borrowed = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &borrower_cap, &mut market, &coin_registry,
            borrow_amount, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed);

        // Step 4: Drop ETH price → position liquidatable
        // Weighted collateral = $600 * 70% = $420 < $500 debt
        clock.set_for_testing(101_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(600, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 5: Liquidator provides only 1 raw USDC ($0.000001)
        // This simulates a dust position where the TOTAL remaining debt
        // is so small that the full repay amount produces seize = 0.
        //
        // seize_ctokens = 1 * 1.05 * $1/10^6 / $600 * 10^8 / 1.0
        //               = 1.05 * 100 / (600 * 10^6)
        //               = 105 / 600_000_000
        //               ≈ 0.000000175
        // floor(0.000000175) = 0
        //
        // At reserve.move:171: assert!(ctokens.value() > 0) → ABORT
        scenario.next_tx(LIQUIDATOR);
        let dust_repay = sui::coin::mint_for_testing<USDC>(1, scenario.ctx());

        let permit = protocol::whitelist_admin::mint_new_whitelist(
            &admin_cap, &mut app, scenario.ctx()
        );
        protocol::whitelist_admin::update_permission(
            &admin_cap, &mut app, object::id(&permit),
            protocol::whitelist_admin::liquidation(), true
        );

        // This ABORTS because seize_ctokens.floor() = 0
        let (seized, refund) =
            protocol::liquidate::liquidate_as_coin<MainMarket, USDC, ETH>(
                &app, &permit, borrower_cap.id(), &mut market,
                dust_repay, &coin_registry, &x_oracle, &clock, scenario.ctx()
            );

        // Never reached — test passes via #[expected_failure]
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
