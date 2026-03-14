// PoC for Report #044: Non-Collateral Deposit Interest Skip on Withdraw
//
// Target: contracts/protocol/sources/internal/market/market.move:858-886
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_044
//
// Bug: refresh_obligation_assets_interest skips accrue_interest for deposits
// where can_be_collateral() == false (liquidation_factor = 0). When the user
// withdraws, burn_ctokens uses a stale exchange rate, causing the depositor
// to receive fewer underlying tokens than entitled (zero interest earned).

#[test_only]
module protocol::poc_044_non_collateral_interest_skip {
    use sui::test_scenario;
    use sui::clock;
    use sui::coin::Coin;

    use protocol::market_t::MainMarket;
    use test_coin::eth::ETH;
    use test_coin::usdc::USDC;
    use protocol::oracle_t;
    use protocol::open_obligation_t;
    use protocol::constants;
    use protocol::market_t::default_eth_decimal_places;
    use protocol::market_t::default_stable_decimal_places;

    const ADMIN: address = @0xAD;
    const DEPOSITOR: address = @0xBB;
    const BORROWER: address = @0xCC;

    /// Proves that a depositor of a non-collateral asset earns ZERO interest
    /// despite the asset being actively borrowed for an extended period.
    ///
    /// Setup:
    ///   1. Create eMode group 1 with ETH as non-collateral (liquidation_factor=0)
    ///   2. Depositor enters group 1, deposits 100 ETH
    ///   3. Borrower (default group 0) borrows 50 ETH, generating interest
    ///   4. After 10,000,000 seconds (~115 days), Depositor withdraws all ETH
    ///
    /// Result:
    ///   BUG:   amount_received == 100 ETH (zero interest earned)
    ///   FIXED: amount_received >  100 ETH (interest accrued correctly)
    ///
    /// The test PASSES because the Depositor gets exactly their initial deposit
    /// back with zero interest — proving the stale exchange rate bug.
    #[test]
    fun test_non_collateral_withdrawal_earns_zero_interest() {
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

        // Step 3: Onboard ETH to group 1 as NON-COLLATERAL (lf=0, cf=0)
        let dep_lim = protocol::emode_admin::create_limiter(
            &admin_cap, &app, 2u64.pow(63), 10_000_000u32, 10_000_000u32);
        let bor_lim = protocol::emode_admin::create_limiter(
            &admin_cap, &app, 2u64.pow(63), 10_000_000u32, 10_000_000u32);
        let eth_params = protocol::emode_admin::create_emode_params_test(
            &admin_cap,
            0,    // collateral_factor_bps = 0
            0,    // liquidation_factor_bps = 0 → can_be_collateral() returns false
            0,    // liquidation_incentive_bps
            constants::max_borrow_amount(),
            constants::borrow_weight_rate(),
            constants::flash_loan_fee_rate(),
            dep_lim, bor_lim
        );
        protocol::emode_admin::onboard_asset_to_emode_group<MainMarket, ETH>(
            &admin_cap, &app, &mut market, 1, eth_params, scenario.ctx()
        );

        // Step 4: Set oracle prices
        clock.set_for_testing(300_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 5: Depositor enters eMode group 1, deposits 100 ETH (non-collateral)
        let eth_deposit = 100 * 10u64.pow(default_eth_decimal_places()); // 100 ETH
        scenario.next_tx(DEPOSITOR);
        let depositor_cap = protocol::enter_market::create_obligation_with_group<MainMarket>(
            &app, &mut market, 1, scenario.ctx()
        );
        let eth_coin = sui::coin::mint_for_testing<ETH>(eth_deposit, scenario.ctx());
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &depositor_cap, eth_coin, &clock, scenario.ctx()
        );
        // Depositor has 100*10^8 = 10,000,000,000 cETH at exchange_rate=1.0

        // Step 6: Borrower (default group 0) deposits USDC collateral and borrows ETH
        scenario.next_tx(BORROWER);
        let borrower_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let usdc_amount = 100_000 * 10u64.pow(default_stable_decimal_places());
        let usdc_coin = sui::coin::mint_for_testing<USDC>(usdc_amount, scenario.ctx());
        protocol::deposit::deposit<MainMarket, USDC>(
            &app, &mut market, &borrower_cap, usdc_coin, &clock, scenario.ctx()
        );
        scenario.next_tx(BORROWER);
        let eth_borrow = 50 * 10u64.pow(default_eth_decimal_places()); // 50 ETH
        let borrowed = protocol::borrow::borrow<MainMarket, ETH>(
            &app, &borrower_cap, &mut market, &coin_registry,
            eth_borrow, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed);
        // ETH reserve now has 50 ETH of outstanding debt generating interest

        // Step 7: Advance time by 10,000,000 seconds (~115 days)
        // Do NOT touch the ETH reserve — no deposits, borrows, or repays
        clock.set_for_testing(10_000_300_000); // T=10,000,300 seconds (in ms)

        // Step 8: Depositor withdraws ALL ETH cTokens
        // BUG: refresh_obligation_assets_interest (market.move:882) skips
        //      accrue_interest for ETH because can_be_collateral() == false.
        //      burn_ctokens uses stale exchange_rate from T=300 → no interest.
        //
        // The Depositor has no debt, so the safety check (is_obligation_safe)
        // passes without querying any oracle prices.
        scenario.next_tx(DEPOSITOR);
        protocol::withdraw::withdraw<MainMarket, ETH>(
            &app, &mut market, &depositor_cap, &coin_registry,
            eth_deposit, // withdraw all cTokens (minted at 1:1)
            &x_oracle, &clock, scenario.ctx()
        );

        // Step 9: Verify Depositor got EXACTLY initial deposit — ZERO interest
        test_scenario::next_tx(scenario, DEPOSITOR);
        let refunded = scenario.take_from_sender<Coin<ETH>>();

        // BUG PROVEN: amount_received == initial_deposit (no interest earned)
        // After 115 days of lending at ~4.5% utilization, this should be > eth_deposit
        assert!(refunded.value() == eth_deposit, 0);

        // Cleanup
        std::unit_test::destroy(refunded);
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(depositor_cap);
        std::unit_test::destroy(borrower_cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(x_oracle);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
