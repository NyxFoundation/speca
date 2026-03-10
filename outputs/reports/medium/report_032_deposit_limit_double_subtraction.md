### Deposit Limit Check Double-Subtracts `cash_reserve`, Allowing Limit Bypass

Depositor will bypass the configured deposit limit in any market with non-zero `cash_reserve`

### Summary

Double-subtraction of `cash_reserve` in `deposit_limit_breached` will cause a deposit limit bypass for protocol administrators as any depositor will deposit beyond the configured `max_deposit_amount` by approximately the value of `cash_reserve`

### Root Cause

In [`reserve.move:87-89`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/reserve.move#L87-L89) the `deposit_limit_breached` function explicitly subtracts `self.cash_reserve.ceil()` from the total, but `total_deposit_plus_interest()` already excludes `cash_reserve` because the underlying [`exchange_rate`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/reserve.move#L92-L101) uses `cash_plus_borrows_minus_reserves()` (= `debt + cash - cash_reserve`) as its numerator:

```move
public(package) fun deposit_limit_breached<MarketType>(self: &Reserve<MarketType>, increment: u64, limit: u64): bool {
    let total_deposit_plus_interest = self.total_deposit_plus_interest();
    total_deposit_plus_interest.ceil() + increment - self.cash_reserve.ceil() > limit
}
```

`total_deposit_plus_interest()` (line 82-84) calls `self.exchange_rate().mul_u64(self.total_supply)`.

The exchange rate (line 92-101) is:
```move
public(package) fun exchange_rate<MarketType>(self: &Reserve<MarketType>): Decimal {
    if (self.total_supply == 0) { return float::from_quotient(1, 1) };
    let numerator = self.cash_plus_borrows_minus_reserves(); // = debt + cash - cash_reserve
    let denominator = float::from(self.total_supply);
    numerator.div(denominator)
}
```

So `total_deposit_plus_interest = (debt + cash - cash_reserve) / total_supply * total_supply = debt + cash - cash_reserve`.

The final check becomes:
```
(debt + cash - cash_reserve).ceil() + increment - cash_reserve.ceil() > limit
```

This simplifies to:
```
debt + cash - 2 * cash_reserve + increment > limit
```

The correct check (to limit total depositor value) should be:
```
total_deposit_plus_interest.ceil() + increment > limit
```

Since `cash_reserve` is subtracted twice, the effective deposit limit is relaxed by `cash_reserve` amount.

### Internal Pre-conditions

1. [Protocol operation needs to accrue fees to set] `cash_reserve` to be at least 1 (from interest reserve factor, flash loan fees, or liquidation revenue)
2. [Admin needs to configure a deposit cap to set] `max_deposit_amount` to be other than 0

### External Pre-conditions

None.

### Attack Path

1. A market operates normally over time, accumulating `cash_reserve` from protocol fees (interest reserve factor, flash loan fees, liquidation revenue).
2. A user calls the deposit function, which triggers `handle_mint` ([`market.move:277-283`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/market.move#L277-L283)).
3. `handle_mint` calls `deposit_limit_breached` to check whether the deposit would exceed the configured limit.
4. `deposit_limit_breached` computes `total_deposit_plus_interest` via [`total_deposit_plus_interest()`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/reserve.move#L82-L84), which already excludes `cash_reserve` through the exchange rate calculation.
5. The function then explicitly subtracts `cash_reserve` again: `total_deposit_plus_interest.ceil() + increment - self.cash_reserve.ceil() > limit`.
6. Because `cash_reserve` is double-subtracted, deposits that should be rejected (exceeding the configured limit) are accepted.

### Impact

The protocol administrators suffer a loss of deposit limit enforcement. As a market matures and protocol reserves grow, the deposit limit becomes increasingly permissive. For example with `max_deposit_amount = 10,000,000 USDC` and `cash_reserve = 500,000 USDC`, the actual effective limit becomes approximately `10,500,000 USDC`, undermining the admin's ability to cap exposure per asset.

### PoC

**File:** `poc_032_deposit_limit_bypass.move`
```move
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
```

### Mitigation

Remove the redundant `cash_reserve` subtraction:

```move
public(package) fun deposit_limit_breached<MarketType>(self: &Reserve<MarketType>, increment: u64, limit: u64): bool {
    let total_deposit_plus_interest = self.total_deposit_plus_interest();
    total_deposit_plus_interest.ceil() + increment > limit
}
```
