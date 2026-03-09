# `deposit_limit_breached` u64 Underflow Aborts and Blocks All Deposits

## Summary

The `deposit_limit_breached` function in reserve.move uses u64 arithmetic that can underflow and abort when accumulated `cash_reserve` exceeds `total_deposit_plus_interest`, blocking all new deposits into the affected market until an admin calls `take_revenue`.

## Vulnerability Detail

In reserve.move:87-90:

```move
public(package) fun deposit_limit_breached<MarketType>(self: &Reserve<MarketType>, increment: u64, limit: u64): bool {
    let total_deposit_plus_interest = self.total_deposit_plus_interest();
    total_deposit_plus_interest.ceil() + increment - self.cash_reserve.ceil() > limit
}
```

This is u64 arithmetic. If `self.cash_reserve.ceil()` exceeds `total_deposit_plus_interest.ceil() + increment`, the subtraction causes a u64 underflow, which in Sui Move aborts the transaction.

This condition can occur when:

1. Protocol accumulates significant `cash_reserve` from interest (via `reserve_factor`) and flash loan fees (via `increase_reserve_only`)
2. Most depositors withdraw their cTokens, reducing `total_supply` to a small value
3. `total_deposit_plus_interest = exchange_rate * total_supply` becomes small
4. `cash_reserve` (accumulated protocol revenue) remains large

Example scenario:
- Over time, 10,000 units of interest accumulate with `reserve_factor = 20%` → `cash_reserve = 2,000`
- Flash loan fees add another 500 → `cash_reserve = 2,500`
- Depositors withdraw until `total_supply = 100` cTokens
- Exchange rate adjusts, but `total_deposit_plus_interest.ceil()` could be, say, 2,000
- A depositor tries to deposit `increment = 100`
- `2,000 + 100 - 2,500 = -400` → u64 underflow → abort

Once in this state, **all new deposits are blocked** because `deposit_limit_breached` is called in `handle_mint` (market.move:278) and always aborts.

Note: This is distinct from report_032 (deposit limit double subtraction) which describes `cash_reserve` being subtracted twice conceptually. This finding is about the u64 arithmetic abort when the result goes negative.

## Internal Pre-conditions

1. cash_reserve must exceed total_deposit_plus_interest + increment (accumulated from reserve_factor interest and flash loan fees).
2. Most depositors must have withdrawn, reducing total_supply to a small value.

## External Pre-conditions

None.

## Attack Path

1. Protocol accumulates 2,500 units of cash_reserve from interest and flash loan fees.
2. Depositors withdraw until total_deposit_plus_interest = 2,000.
3. New user tries to deposit 100 tokens.
4. deposit_limit_breached computes: 2000 + 100 - 2500 = underflow (u64).
5. Transaction aborts, blocking all new deposits.
6. Deposits remain blocked until admin calls take_revenue to drain cash_reserve.

## Impact

New deposits into an affected market are blocked until an admin calls `take_revenue` to drain `cash_reserve`. If `take_revenue` is not called frequently enough, markets with high flash loan activity and low remaining deposits can become deposit-locked, preventing new liquidity from entering.

## Code Snippet

- reserve.move:87-90 (`deposit_limit_breached` with u64 underflow)
- market.move:278 (where `deposit_limit_breached` is called)

## Tool used

Manual Review + Automated Analysis

## Mitigation

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
