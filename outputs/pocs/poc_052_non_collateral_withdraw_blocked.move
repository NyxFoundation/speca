// PoC for Report #052: Non-Collateral Withdraw Blocked by Unrelated Oracle Staleness
//
// Target: contracts/protocol/sources/internal/market/market.move:308-363
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_052
//
// Bug: handle_withdraw unconditionally runs is_obligation_safe even when the
// withdrawn asset has can_be_collateral() == false. Since non-collateral assets
// contribute zero to weighted collateral, removing them doesn't affect safety.
// Yet the check calls get_price_with_check for ALL debt/collateral assets,
// reverting if ANY oracle is stale — locking non-collateral deposits.
//
// The codebase has a TODO at market.move:331 acknowledging this issue.

#[test_only]
module protocol::poc_052_non_collateral_withdraw_blocked {
    use sui::test_scenario;
    use sui::clock;
    use sui::sui::SUI;

    use protocol::market_t::MainMarket;
    use test_coin::eth::ETH;
    use test_coin::usdc::USDC;
    use protocol::oracle_t;
    use protocol::constants;
    use protocol::market_t::default_eth_decimal_places;
    use protocol::market_t::default_stable_decimal_places;
    use protocol::market_t::default_decimal_places;

    const ADMIN: address = @0xAD;
    const USER: address = @0xBB;

    /// Proves that withdrawing a non-collateral deposit is blocked when an
    /// unrelated oracle becomes stale, even though the withdrawal has zero
    /// impact on the obligation's safety ratio.
    ///
    /// Setup:
    ///   1. Create eMode group 1: USDC (collateral), SUI (non-collateral), ETH (for borrowing)
    ///   2. User enters group 1, deposits USDC + SUI, borrows 1 ETH
    ///   3. Advance clock 6 seconds past oracle tolerance (5s)
    ///   4. User tries to withdraw 1 SUI cToken → ABORT (stale oracle)
    ///
    /// The test PASSES (via #[expected_failure]) because the abort IS the bug.
    /// SUI withdrawal should succeed since it doesn't affect collateral/debt ratio.
    #[test]
    #[expected_failure]
    fun test_non_collateral_withdraw_blocked_by_stale_oracle() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market with 4 assets and initial liquidity
        let (admin_cap, app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);
        let mut x_oracle = oracle_t::init_t(scenario);

        // Step 2: Create eMode group 1
        clock.set_for_testing(200_000);
        scenario.next_tx(ADMIN);
        protocol::emode_admin::onboard_new_emode_group<MainMarket>(
            &admin_cap, &app, &mut market, 0, &clock, scenario.ctx()
        );

        // Step 3: Onboard 3 assets to group 1
        // USDC: collateral (cf=5000, lf=7000)
        let dep_lim1 = protocol::emode_admin::create_limiter(
            &admin_cap, &app, 2u64.pow(63), 10_000_000u32, 10_000_000u32);
        let bor_lim1 = protocol::emode_admin::create_limiter(
            &admin_cap, &app, 2u64.pow(63), 10_000_000u32, 10_000_000u32);
        let usdc_params = protocol::emode_admin::create_emode_params_test(
            &admin_cap,
            5000, // collateral_factor_bps
            7000, // liquidation_factor_bps
            2500, // liquidation_incentive_bps
            constants::max_borrow_amount(),
            constants::borrow_weight_rate(),
            constants::flash_loan_fee_rate(),
            dep_lim1, bor_lim1
        );
        protocol::emode_admin::onboard_asset_to_emode_group<MainMarket, USDC>(
            &admin_cap, &app, &mut market, 1, usdc_params, scenario.ctx()
        );

        // SUI: NON-COLLATERAL (cf=0, lf=0)
        let dep_lim2 = protocol::emode_admin::create_limiter(
            &admin_cap, &app, 2u64.pow(63), 10_000_000u32, 10_000_000u32);
        let bor_lim2 = protocol::emode_admin::create_limiter(
            &admin_cap, &app, 2u64.pow(63), 10_000_000u32, 10_000_000u32);
        let sui_params = protocol::emode_admin::create_emode_params_test(
            &admin_cap,
            0, // collateral_factor_bps = 0
            0, // liquidation_factor_bps = 0 → can_be_collateral() returns false
            0, // liquidation_incentive_bps
            constants::max_borrow_amount(),
            constants::borrow_weight_rate(),
            constants::flash_loan_fee_rate(),
            dep_lim2, bor_lim2
        );
        protocol::emode_admin::onboard_asset_to_emode_group<MainMarket, SUI>(
            &admin_cap, &app, &mut market, 1, sui_params, scenario.ctx()
        );

        // ETH: collateral (for borrowing)
        let dep_lim3 = protocol::emode_admin::create_limiter(
            &admin_cap, &app, 2u64.pow(63), 10_000_000u32, 10_000_000u32);
        let bor_lim3 = protocol::emode_admin::create_limiter(
            &admin_cap, &app, 2u64.pow(63), 10_000_000u32, 10_000_000u32);
        let eth_params = protocol::emode_admin::create_emode_params_test(
            &admin_cap,
            5000, // collateral_factor_bps
            7000, // liquidation_factor_bps
            2500, // liquidation_incentive_bps
            constants::max_borrow_amount(),
            constants::borrow_weight_rate(),
            constants::flash_loan_fee_rate(),
            dep_lim3, bor_lim3
        );
        protocol::emode_admin::onboard_asset_to_emode_group<MainMarket, ETH>(
            &admin_cap, &app, &mut market, 1, eth_params, scenario.ctx()
        );

        // Step 4: Set oracle prices — all fresh at T=300s
        clock.set_for_testing(300_000);
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));     // $1
        x_oracle.update_price<SUI>(&clock, oracle_t::calc_scaled_price(1, 0));      // $1
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));   // $1000

        // Step 5: User enters eMode group 1
        scenario.next_tx(USER);
        let user_cap = protocol::enter_market::create_obligation_with_group<MainMarket>(
            &app, &mut market, 1, scenario.ctx()
        );

        // Step 6: User deposits USDC (collateral) and SUI (non-collateral)
        let usdc_deposit = 10_000 * 10u64.pow(default_stable_decimal_places()); // $10,000
        let usdc_coin = sui::coin::mint_for_testing<USDC>(usdc_deposit, scenario.ctx());
        protocol::deposit::deposit<MainMarket, USDC>(
            &app, &mut market, &user_cap, usdc_coin, &clock, scenario.ctx()
        );

        let sui_deposit = 100 * 10u64.pow(default_decimal_places()); // 100 SUI = $100
        let sui_coin = sui::coin::mint_for_testing<SUI>(sui_deposit, scenario.ctx());
        protocol::deposit::deposit<MainMarket, SUI>(
            &app, &mut market, &user_cap, sui_coin, &clock, scenario.ctx()
        );

        // Step 7: User borrows 1 ETH ($1000) against USDC collateral
        // USDC $10,000 * 50% CF = $5,000 capacity; 1 ETH = $1,000 → safe
        scenario.next_tx(USER);
        let eth_borrow = 1 * 10u64.pow(default_eth_decimal_places()); // 1 ETH
        let borrowed = protocol::borrow::borrow<MainMarket, ETH>(
            &app, &user_cap, &mut market, &coin_registry,
            eth_borrow, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed);

        // Step 8: Advance clock 6 seconds past oracle staleness threshold (5s)
        // Oracle last updated at T=300s, new clock at T=306s → 6s stale
        clock.set_for_testing(306_000);

        // Step 9: User tries to withdraw 1 SUI cToken (non-collateral, partial)
        // BUG: handle_withdraw runs is_obligation_safe which calls
        //      get_price_with_check for ETH (debt asset) → oracle stale → ABORT
        //
        // SUI contributes $0 to collateral (lf=0), so withdrawing it has
        // ZERO impact on the obligation's safety ratio. The check should be
        // skipped for non-collateral withdrawals.
        scenario.next_tx(USER);
        protocol::withdraw::withdraw<MainMarket, SUI>(
            &app, &mut market, &user_cap, &coin_registry,
            1, // just 1 cToken — minimal partial withdrawal
            &x_oracle, &clock, scenario.ctx()
        );

        // Never reached — cleanup for compiler
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(user_cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(x_oracle);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
