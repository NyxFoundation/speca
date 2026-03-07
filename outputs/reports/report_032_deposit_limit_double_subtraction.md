# Deposit Limit Check Double-Subtracts `cash_reserve`, Allowing Limit Bypass

## Summary

`deposit_limit_breached` in `reserve.move` subtracts `cash_reserve` twice — once implicitly via `total_deposit_plus_interest` (which uses `exchange_rate`, already excluding `cash_reserve`) and once explicitly. This makes the deposit limit more permissive than configured by approximately the value of `cash_reserve`.

## Vulnerability Detail

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

So `total_deposit_plus_interest = (debt + cash - cash_reserve) / total_supply * total_supply ≈ debt + cash - cash_reserve`.

The final check becomes:
```
(debt + cash - cash_reserve).ceil() + increment - cash_reserve.ceil() > limit
```

This simplifies to approximately:
```
debt + cash - 2 * cash_reserve + increment > limit
```

The correct check (to limit total depositor value) should be:
```
total_deposit_plus_interest.ceil() + increment > limit
```

Since `cash_reserve` is subtracted twice, the effective deposit limit is relaxed by `cash_reserve` amount.

## Impact

As a market matures and protocol reserves grow (from interest reserve factor, flash loan fees, liquidation revenue), the deposit limit becomes increasingly permissive. For example:

- Configured `max_deposit_amount = 10,000,000 USDC`
- After significant activity, `cash_reserve = 500,000 USDC`
- Actual effective limit becomes approximately `10,500,000 USDC`

This undermines the admin's ability to cap exposure per asset, which is a critical risk management control.

## Code Snippet

- `reserve.move:87-89` — `deposit_limit_breached` function
- `reserve.move:82-84` — `total_deposit_plus_interest` (already excludes `cash_reserve`)
- `reserve.move:92-101` — `exchange_rate` (numerator = `cash + debt - cash_reserve`)
- `market.move:277-283` — `handle_mint` calls `deposit_limit_breached`

## Tool used

Manual Review + Automated Analysis

## Recommendation

Remove the redundant `cash_reserve` subtraction:

```move
public(package) fun deposit_limit_breached<MarketType>(self: &Reserve<MarketType>, increment: u64, limit: u64): bool {
    let total_deposit_plus_interest = self.total_deposit_plus_interest();
    total_deposit_plus_interest.ceil() + increment > limit
}
```
