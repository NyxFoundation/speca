// PoC for Report #032: Deposit Limit Double-Subtraction of cash_reserve
//
// Target: contracts/protocol/sources/internal/market/reserve.move:87-89
// Place in: contracts/protocol/sources/internal/market/ (or tests/ directory)
// Run:   sui move test --filter poc_032

#[test_only]
module protocol::poc_032_deposit_limit_bypass {
    use math::float;
    use protocol::reserve;

    public struct PoCMarket {}
    public struct PoCCoin {}

    /// Proves that deposit_limit_breached allows deposits beyond the configured
    /// limit when cash_reserve > 0. The bug: cash_reserve is subtracted twice —
    /// once inside exchange_rate (via cash_plus_borrows_minus_reserves) and once
    /// explicitly in the limit check formula.
    ///
    /// Setup:
    ///   deposit 10000, borrow 5000, accrue 100% interest (interest = 5000)
    ///   → cash=5000, debt=10000, cash_reserve=1000 (20% of interest)
    ///   → total_deposit_plus_interest = (5000+10000-1000)/10000 * 10000 = 14000
    ///
    /// Buggy check:  14000 + 600 - 1000 = 13600 ≤ 14500 → NOT breached (false)
    /// Correct check: 14000 + 600 = 14600 > 14500 → SHOULD be breached (true)
    ///
    /// The test PASSES, proving the deposit is wrongly allowed beyond the limit.
    #[test]
    fun test_deposit_allowed_beyond_configured_limit() {
        let admin = @0xAD;
        let mut scenario_value = sui::test_scenario::begin(admin);
        let ctx = scenario_value.ctx();
        let mut reserve = reserve::new<PoCMarket, PoCCoin>(ctx, 0);

        // Step 1: Deposit 10,000 tokens
        let deposit_coin = sui::balance::create_for_testing<PoCCoin>(10000).into_coin(ctx);
        let ctokens = reserve.mint_ctokens<PoCMarket, PoCCoin>(deposit_coin);
        // State: cash=10000, supply=10000, exchange_rate=1.0

        // Step 2: Borrow 5,000
        let borrowed = reserve.borrow_amount<PoCMarket, PoCCoin>(5000);
        // State: cash=5000, debt=5000, supply=10000

        // Step 3: Accrue interest
        //   interest_rate = 0.1/time, time_delta = 10 → simple_interest_factor = 1.0
        //   interest_accumulated = 5000 * 1.0 = 5000
        //   debt → 5000 + 5000 = 10000
        //   cash_reserve → 0 + 0.2 * 5000 = 1000
        let reserve_factor = float::from_quotient(1, 5);  // 20%
        let interest_rate = float::from_quotient(1, 10);   // 10% per time unit
        reserve.accrue_interest(reserve_factor, interest_rate, 10);
        // State: cash=5000, debt=10000, cash_reserve=1000, supply=10000
        // exchange_rate = (5000+10000-1000)/10000 = 1.4
        // total_deposit_plus_interest = 14000

        // Step 4: Attempt deposit of 600 against limit of 14500
        let limit = 14500u64;
        let increment = 600u64;
        let is_breached = reserve.deposit_limit_breached(increment, limit);

        // BUG: returns false — deposit wrongly allowed
        // Buggy formula: 14000 + 600 - 1000 = 13600 ≤ 14500
        assert!(!is_breached, 0);

        // Verify that REAL depositor exposure exceeds configured limit
        let real_exposure = reserve.total_deposit_plus_interest().ceil() + increment;
        assert!(real_exposure > limit, 1); // 14600 > 14500

        // Cleanup
        sui::balance::destroy_for_testing(borrowed);
        std::unit_test::destroy(ctokens);
        std::unit_test::destroy(reserve);
        scenario_value.end();
    }
}
