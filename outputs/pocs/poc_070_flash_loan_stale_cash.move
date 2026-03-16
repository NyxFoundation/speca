/// PoC: Flash loan does not update reserve.cash, creating state inconsistency
///
/// This test demonstrates that during an active flash loan, `reserve.cash`
/// is stale (not decremented), while `underlying_balance` has been reduced.
/// This inconsistency means the `borrow_amount` availability check could pass
/// even when insufficient tokens remain in the pool.
///
/// Note: The actual exploitation is limited because `withdraw_underlying`
/// will abort if `underlying_balance` is insufficient. But the invariant
/// violation (cash != underlying_balance.value()) is demonstrated.
module protocol::poc_flash_loan_stale_cash {
    use sui::test_scenario;
    use math::float;

    #[test_only]
    public struct TestMarket {}

    #[test_only]
    public struct BTC {}

    /// Demonstrates the state inconsistency during a flash loan
    #[test]
    fun test_flash_loan_cash_not_updated() {
        let admin = @0xAD;
        let mut scenario = test_scenario::begin(admin);
        let ctx = scenario.ctx();

        let mut reserve = protocol::reserve::new<TestMarket, BTC>(ctx, 1);

        // Setup: deposit 1000 BTC
        let btc = sui::balance::create_for_testing<BTC>(1000).into_coin(ctx);
        let ctokens = reserve.mint_ctokens<TestMarket, BTC>(btc).into_coin(ctx);

        // Verify initial state: cash should equal 1000
        assert!(reserve.exchange_rate() == float::from_quotient(1, 1));

        // Take a flash loan of 900
        let (borrowed, loan) = reserve.borrow_flash_loan<TestMarket, BTC>(900);

        // CRITICAL: During flash loan, exchange_rate still uses the stale cash
        // exchange_rate = (cash + debt - cash_reserve) / total_supply
        // = (1000 + 0 - 0) / 1000 = 1.0
        // But underlying_balance is only 100!
        assert!(reserve.exchange_rate() == float::from_quotient(1, 1));

        // The cash field is stale - it still shows 1000 even though
        // only 100 tokens remain in underlying_balance
        // This means borrow_amount's check: self.cash - self.cash_reserve.ceil() > amount
        // would pass for amounts up to ~999, even though only 100 tokens are available

        // Repay the flash loan
        let repay_btc = sui::balance::create_for_testing<BTC>(900).into_coin(ctx);
        let fee_btc = sui::balance::create_for_testing<BTC>(1).into_coin(ctx);
        reserve.repay_flash_loan(loan, repay_btc, fee_btc);

        // After repay: cash should be 1001 (original 1000 + 1 fee via increase_reserve_only)
        // cash_reserve should be 1 (the fee)
        // exchange_rate = (1001 + 0 - 1) / 1000 = 1.0 (fee goes to cash_reserve)
        assert!(reserve.exchange_rate() == float::from_quotient(1, 1));

        // Cleanup
        std::unit_test::destroy(borrowed);
        std::unit_test::destroy(ctokens);
        std::unit_test::destroy(reserve);
        scenario.end();
    }
}
