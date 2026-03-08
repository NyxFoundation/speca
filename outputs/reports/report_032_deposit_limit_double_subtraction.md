# Deposit Limit Check Double-Subtracts `cash_reserve`, Allowing Limit Bypass

## Summary

`deposit_limit_breached` in `reserve.move` subtracts `cash_reserve` twice -- once implicitly via `total_deposit_plus_interest` (which uses `exchange_rate`, already excluding `cash_reserve`) and once explicitly. This makes the deposit limit more permissive than configured by approximately the value of `cash_reserve`.

## Root Cause

In [`reserve.move:87-89`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/reserve.move#L87-L89), the `deposit_limit_breached` function explicitly subtracts `self.cash_reserve.ceil()` from the total, but `total_deposit_plus_interest()` already excludes `cash_reserve` because the underlying [`exchange_rate`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/reserve.move#L92-L101) uses `cash_plus_borrows_minus_reserves()` (= `debt + cash - cash_reserve`) as its numerator. This results in `cash_reserve` being subtracted twice, relaxing the effective deposit limit.

## Internal Pre-conditions

1. The market must have accumulated a non-zero `cash_reserve` (from interest reserve factor, flash loan fees, or liquidation revenue).
2. The admin must have configured a `max_deposit_amount` limit for the market.

## External Pre-conditions

1. None. The bug is triggered through normal protocol operation whenever deposits are made and `cash_reserve > 0`.

## Attack Path

1. A market operates normally over time, accumulating `cash_reserve` from protocol fees (interest reserve factor, flash loan fees, liquidation revenue).
2. A user calls the deposit function, which triggers `handle_mint` ([`market.move:277-283`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/market.move#L277-L283)).
3. `handle_mint` calls `deposit_limit_breached` to check whether the deposit would exceed the configured limit.
4. `deposit_limit_breached` computes `total_deposit_plus_interest` via [`total_deposit_plus_interest()`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/reserve.move#L82-L84), which already excludes `cash_reserve` through the exchange rate calculation.
5. The function then explicitly subtracts `cash_reserve` again: `total_deposit_plus_interest.ceil() + increment - self.cash_reserve.ceil() > limit`.
6. Because `cash_reserve` is double-subtracted, deposits that should be rejected (exceeding the configured limit) are accepted.

## Impact

As a market matures and protocol reserves grow, the deposit limit becomes increasingly permissive. For example:

- Configured `max_deposit_amount = 10,000,000 USDC`
- After significant activity, `cash_reserve = 500,000 USDC`
- Actual effective limit becomes approximately `10,500,000 USDC`

This undermines the admin's ability to cap exposure per asset, which is a critical risk management control.

## PoC

The `deposit_limit_breached` function (reserve.move:87-89) computes:

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

## Tool used

Manual Review + Automated Analysis

## Mitigation

Remove the redundant `cash_reserve` subtraction:

```move
public(package) fun deposit_limit_breached<MarketType>(self: &Reserve<MarketType>, increment: u64, limit: u64): bool {
    let total_deposit_plus_interest = self.total_deposit_plus_interest();
    total_deposit_plus_interest.ceil() + increment > limit
}
```
