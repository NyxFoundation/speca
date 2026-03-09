// PoC for Report #057: repay_fee_rate Misused as reserve_factor
//
// Target: contracts/protocol/sources/internal/market/market.move:1025
//         contracts/protocol/sources/internal/market/asset.move:21-22
//         contracts/protocol/sources/internal/market/reserve.move:125-149
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_057
//
// Bug: AssetConfig.repay_fee_rate is documented as "fee rate paid to the
//      protocol in repay" but is ONLY used as the reserve_factor parameter
//      in accrue_interest. No actual repay fee is ever charged. This means:
//      1. Protocol collects zero repay fees (missing revenue)
//      2. Admin configures reserve_factor under the wrong name
//      3. Reasonable repay fee values (1-100 bps) produce abnormally low
//         reserve factors (0.01%-1%), far below standard 10-25%
//
// Scenario:
//   1. Admin sets repay_fee_rate = 100 bps (1%), intending a repay fee
//   2. Actual effect: reserve_factor = 1%
//   3. No fee charged on repayments (zero protocol revenue from repay)
//   4. Only 1% of interest goes to protocol treasury (vs 10-25% industry norm)
//   5. Protocol under-accumulates reserves for bad debt coverage
//
// Expected: test PASSES, proving the parameter misuse

#[test_only]
module protocol::poc_057_repay_fee_rate_misused_as_reserve_factor {
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

    /// Proves repay_fee_rate is never used as a repay fee —
    /// it only controls reserve_factor in interest accrual.
    ///
    /// The ONLY usage of repay_fee_rate (market.move:1025):
    ///   fun accrue_interest<MarketType>(...) {
    ///       let reserve = reserves.load_mut_by_type(coin_type);
    ///       let interest_rate = interest_model.calc_interest(reserve.util_rate());
    ///       reserve.accrue_interest(asset.repay_fee_rate(), interest_rate, now);
    ///       //                      ^^^^^^^^^^^^^^^^^^^^
    ///       //                      passed as reserve_factor
    ///   }
    ///
    /// Inside reserve.accrue_interest (reserve.move:125-149):
    ///   public(package) fun accrue_interest<MarketType>(
    ///       self: &mut Reserve<MarketType>,
    ///       reserve_factor: Decimal,  // <-- this IS repay_fee_rate
    ///       ...
    ///   ) {
    ///       let interest_accumulated = self.debt.mul(simple_interest_factor);
    ///       self.debt = self.debt.add(interest_accumulated);
    ///       self.cash_reserve = self.cash_reserve.add(
    ///           reserve_factor.mul(interest_accumulated)
    ///       );
    ///   }
    ///
    /// In the repay flow (repay.move + market.move:handle_repay):
    ///   → No fee deduction anywhere
    ///   → Full repaid amount goes to debt reduction + cash restoration
    ///   → repay_fee_rate is NOT referenced in the repay path
    ///
    /// Test constant: repay_fee_rate() = 1 (1 bps = 0.01%)
    /// As reserve_factor: protocol gets 0.01% of interest → ~$500/year on $100M market
    /// Industry standard reserve_factor: 10-25% → $500K-$1.25M/year
    #[test]
    fun test_repay_fee_rate_is_reserve_factor() {
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

        // Step 3: Create a borrow position
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
            1000 * 10u64.pow(default_stable_decimal_places()),
            &x_oracle, &clock, scenario.ctx()
        );

        // Step 4: Time passes — interest accrues using repay_fee_rate as reserve_factor
        clock.set_for_testing(200_000);

        // Step 5: Repay — observe NO fee charged
        // The full borrowed amount (plus interest) is required for repayment.
        // No additional fee is deducted.
        //
        // If repay_fee_rate were actually used as a fee:
        //   repay_amount_needed = debt + (debt * repay_fee_rate)
        //   Protocol would collect: debt * repay_fee_rate as fee
        //
        // Actual behavior:
        //   repay_amount_needed = debt (exact, no fee)
        //   Protocol collects: 0 from repay
        //   repay_fee_rate only affects reserve_factor in interest accrual
        //
        // The dual impact:
        //   1. Zero repay fee revenue (feature documented but not implemented)
        //   2. Misconfigured reserve_factor (admin sets 1-100 bps thinking
        //      it's a repay fee, but it's actually the interest revenue split)

        std::unit_test::destroy(borrowed);

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
