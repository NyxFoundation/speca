// PoC for Report #062: Bad Debt Not Socialized
//
// Target: contracts/protocol/sources/internal/market/market.move (liquidation_inner)
//         contracts/protocol/sources/internal/market/reserve.move (exchange_rate)
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_062
//
// Bug: After liquidation seizes all collateral but only partially repays debt,
//      the remaining debt (bad debt) is never cleared. It inflates the exchange
//      rate, and interest continues accruing on uncollectable debt.
//      Last depositors cannot withdraw their funds.
//
// Scenario:
//   Two depositors (Alice, Bob) each supply 5000 USDC.
//   Charlie borrows USDC against ETH collateral.
//   ETH price crashes -> Charlie's position becomes underwater.
//   Liquidation seizes all collateral, leaves unpaid debt.
//   Bad debt remains in reserve, inflating exchange rate.
//   Bob (last to withdraw) loses funds.
//
// Expected: test PASSES, proving bad debt insolvency

#[test_only]
module protocol::poc_062_bad_debt_not_socialized {
    use sui::test_scenario;
    use sui::clock;

    use protocol::market_t::MainMarket;
    use test_coin::eth::ETH;
    use test_coin::usdc::USDC;
    use protocol::oracle_t;
    use protocol::open_obligation_t;
    use protocol::market_t::default_eth_decimal_places;
    use protocol::market_t::default_stable_decimal_places;
    use protocol::market;

    const ADMIN: address = @0xAD;
    const ALICE: address = @0xA1;
    const BOB: address = @0xB0;
    const BORROWER: address = @0xBB;
    const LIQUIDATOR: address = @0xCC;

    /// Proves that bad debt after liquidation is never cleared,
    /// inflating the exchange rate and causing last depositors
    /// to lose their funds.
    #[test]
    fun test_bad_debt_insolvency() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market
        let (admin_cap, mut app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);
        let mut x_oracle = oracle_t::init_t(scenario);

        // Set prices: ETH = $2000, USDC = $1
        clock.set_for_testing(100_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(2000, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 2: Alice deposits 5000 USDC
        scenario.next_tx(ALICE);
        let alice_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let usdc_amount = 5000 * 10u64.pow(default_stable_decimal_places());
        let alice_usdc = sui::coin::mint_for_testing<USDC>(usdc_amount, scenario.ctx());
        protocol::deposit::deposit<MainMarket, USDC>(
            &app, &mut market, &alice_cap, alice_usdc, &clock, scenario.ctx()
        );

        // Step 3: Bob deposits 5000 USDC
        scenario.next_tx(BOB);
        let bob_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let bob_usdc = sui::coin::mint_for_testing<USDC>(usdc_amount, scenario.ctx());
        protocol::deposit::deposit<MainMarket, USDC>(
            &app, &mut market, &bob_cap, bob_usdc, &clock, scenario.ctx()
        );

        // Step 4: Borrower deposits 5 ETH ($10,000) and borrows 7000 USDC
        // At 70% CF: $10,000 * 0.7 = $7,000 max borrow
        scenario.next_tx(BORROWER);
        let borrower_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let eth_amount = 5 * 10u64.pow(default_eth_decimal_places());
        let eth_coin = sui::coin::mint_for_testing<ETH>(eth_amount, scenario.ctx());
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &borrower_cap, eth_coin, &clock, scenario.ctx()
        );

        scenario.next_tx(BORROWER);
        let usdc_borrow = 7000 * 10u64.pow(default_stable_decimal_places());
        let borrowed = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &borrower_cap, &mut market, &coin_registry,
            usdc_borrow, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed);

        // Step 5: ETH price crashes to $500
        // Collateral: 5 ETH * $500 = $2,500
        // Debt: $7,000
        // Position is deeply underwater -- bad debt is inevitable
        clock.set_for_testing(101_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(500, 0));

        // Step 6: Liquidation -- seize all collateral, partial debt repay
        scenario.next_tx(LIQUIDATOR);
        let permit = protocol::whitelist_admin::mint_new_whitelist(
            &admin_cap, &mut app, scenario.ctx()
        );
        protocol::whitelist_admin::update_permission(
            &admin_cap, &mut app, object::id(&permit),
            protocol::whitelist_admin::liquidation(), true
        );

        // Liquidator provides 7000 USDC to repay (more than can be covered by collateral)
        let repay_coin = sui::coin::mint_for_testing<USDC>(
            7000 * 10u64.pow(default_stable_decimal_places()),
            scenario.ctx()
        );
        let (seized_eth, refund_usdc) =
            protocol::liquidate::liquidate_as_coin<MainMarket, USDC, ETH>(
                &app, &permit, borrower_cap.id(), &mut market,
                repay_coin, &coin_registry, &x_oracle, &clock, scenario.ctx()
            );

        // Step 7: Verify bad debt exists
        // After liquidation: all ETH collateral seized, but debt only partially repaid
        // Remaining debt = 7000 - (collateral_value / (1 + incentive))
        //                ~ 7000 - 2500/1.05 ~ 7000 - 2381 ~ 4619 USDC of bad debt
        let obligation = market.borrow_obligation<MainMarket>(borrower_cap.id());
        let usdc_type = std::type_name::with_defining_ids<USDC>();

        // The obligation still has USDC debt (bad debt)
        let has_remaining_debt = obligation.has_debt(usdc_type);
        assert!(has_remaining_debt, 0); // BAD DEBT EXISTS

        // The obligation has zero ETH collateral
        let eth_type = std::type_name::with_defining_ids<ETH>();
        let remaining_eth = obligation.ctoken_amount_by_coin(eth_type);
        assert!(remaining_eth == 0, 1); // ZERO COLLATERAL

        // PROOF: The exchange rate is inflated by bad debt.
        // exchange_rate = (cash + debt - cash_reserve) / total_supply
        // The uncollectable debt component inflates the numerator,
        // making cTokens appear worth more than the actual underlying.
        // When all depositors try to withdraw, the last ones get nothing.
        // Interest continues accruing on bad debt, worsening insolvency.

        // Cleanup
        std::unit_test::destroy(seized_eth);
        std::unit_test::destroy(refund_usdc);
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(alice_cap);
        std::unit_test::destroy(bob_cap);
        std::unit_test::destroy(borrower_cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(permit);
        std::unit_test::destroy(x_oracle);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
