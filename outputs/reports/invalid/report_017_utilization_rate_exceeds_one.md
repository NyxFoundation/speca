# Utilization Rate Can Exceed 1.0 Causing Interest Rate Runaway

## Summary

The utilization rate calculation `debt / (cash + debt - reserves)` has no cap at 1.0. When `cash_reserve` grows from flash loan fees or repayment excess, the denominator shrinks below `debt`, pushing utilization above 100%. This causes the interest rate model to compute unboundedly high borrow rates.

## Vulnerability Detail

In `reserve.move:65-76`:

```move
public(package) fun util_rate<MarketType>(self: &Reserve<MarketType>): Decimal {
    if (self.debt.is_zero()) {
        return float::from_quotient(0, 1)
    };
    let denominator = self.cash_plus_borrows_minus_reserves();
    self.debt.div(denominator)  // No cap at 1.0
}

public(package) fun cash_plus_borrows_minus_reserves<MarketType>(self: &Reserve<MarketType>): Decimal {
    self.debt.add_u64(self.cash).sub(self.cash_reserve)
}
```

The formula is `util = debt / (cash + debt - cash_reserve)`. If `cash_reserve > cash` (possible via accumulated protocol fees), then `(cash + debt - cash_reserve) < debt`, and `util > 1.0`.

The interest model in `interest.move:85-96` does handle `util > high_kink` but the linear extrapolation produces unboundedly high rates:

```move
// When util > high_kink (e.g., 0.9):
// rate = base + kink_rate + slope * (util - high_kink) / (1 - high_kink)
// If util = 1.5 and high_kink = 0.9:
// slope * (1.5 - 0.9) / (1.0 - 0.9) = slope * 6.0 (600% of max slope!)
```

## Impact

- **Interest rate explosion**: Borrow rates can spike to extreme values when utilization exceeds 1.0, rapidly compounding debt for existing borrowers
- **Cascading liquidations**: Extreme interest rates push obligations underwater, triggering mass liquidations
- **Protocol insolvency risk**: If rates grow faster than liquidation can clear bad debt, the protocol becomes insolvent

The trigger scenario: heavy flash loan usage or large repayment overpayments accumulate in `cash_reserve`, gradually pushing utilization above 1.0 in low-liquidity markets.

## Code Snippet

- [`reserve.move:65-76`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L65-L76): Uncapped utilization
- [`interest.move:85-96`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/interest.move#L85-L96): Unbounded rate interpolation

## Tool used

Manual Review + Automated Analysis (Codex + Claude cross-validation)

## Recommendation

Cap utilization at 1.0:

```move
public(package) fun util_rate<MarketType>(self: &Reserve<MarketType>): Decimal {
    if (self.debt.is_zero()) {
        return float::from_quotient(0, 1)
    };
    let denominator = self.cash_plus_borrows_minus_reserves();
    let rate = self.debt.div(denominator);
    if (rate.gt(float::from_quotient(1, 1))) {
        float::from_quotient(1, 1)  // Cap at 100%
    } else {
        rate
    }
}
```
