# Simple Interest Accrual Undercharges Borrowers Between Updates

## Summary

The interest accrual formula uses simple interest (`principal * rate * time`) rather than compound interest (`principal * (1 + rate)^time`). Between accrual events, interest does not compound, systematically undercharging borrowers and reducing lender/protocol revenue.

## Vulnerability Detail

In `reserve.move:132-149`:

```move
public(package) fun accrue_interest<MarketType>(..., now: u64) {
    let last_updated = self.borrow_index.last_updated();
    if (last_updated == now) { return };

    let borrow_index_prior = self.borrow_index.value();
    let simple_interest_factor = interest_rate.mul_u64(now - last_updated);  // rate * time
    let interest_accumulated = self.debt.mul(simple_interest_factor);        // debt * rate * time

    self.debt = self.debt.add(interest_accumulated);
    self.cash_reserve = self.cash_reserve.add(reserve_factor.mul(interest_accumulated));

    let new_borrow_index_value = simple_interest_factor.mul(borrow_index_prior).add(borrow_index_prior);
    // new_index = old_index * (1 + rate * time) — simple, not compound
    self.borrow_index.set_value(new_borrow_index_value, now);
}
```

The code comment itself says `simple_interest_factor`. For a 10% annual rate and 1-hour gap between accruals:
- Simple: `principal * 0.10 * (1/8760)` = 0.001142% per hour
- Compound: `principal * ((1 + 0.10/8760)^1 - 1)` ≈ 0.001142% per hour (negligible difference for 1 hour)

But for longer gaps (e.g., 24 hours with no transactions on a low-activity market):
- Simple: `principal * 0.10 * (24/8760)` = 0.02740%
- Compound: `principal * ((1 + 0.10/8760)^24 - 1)` ≈ 0.02741%

The difference is small per-interval but compounds over the year.

## Impact

- **Interest leakage**: Over a full year with daily compounding, the difference is approximately `e^0.10 - 1.10 = 0.52%` — about 0.52% of total debt is not collected
- **Low-activity market amplification**: Markets with infrequent transactions have longer gaps between accruals, increasing the simple-vs-compound gap
- **Standard DeFi pattern**: This matches Compound v2's design and is a known trade-off for gas efficiency

## Code Snippet

- [`reserve.move:139-146`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L139-L146): Simple interest formula

## Tool used

Manual Review + Automated Analysis (Codex + Claude cross-validation)

## Recommendation

Consider per-second compound interest using an exponentiation approximation:

```move
// Taylor approximation: (1 + r)^n ≈ 1 + n*r + n*(n-1)*r^2/2
let elapsed = now - last_updated;
let compound_factor = float::one()
    .add(interest_rate.mul_u64(elapsed))
    .add(interest_rate.mul(interest_rate).mul_u64(elapsed * (elapsed - 1) / 2));
```

Or accept the trade-off and document it as a known design decision.
