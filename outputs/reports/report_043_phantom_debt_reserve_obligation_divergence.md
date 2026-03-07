# Reserve-Level Debt Diverges from Sum of Obligation Debts Creating Phantom Debt

## Summary

Rounding differences between reserve-level and obligation-level interest accrual cause `reserve.debt` to systematically exceed the sum of all individual obligation debts, inflating the exchange rate with uncollectible "phantom debt."

## Vulnerability Detail

Reserve-level interest accrual in `accrue_interest` (reserve.move:125-149) updates debt as:

```move
// reserve.move:139-142
let simple_interest_factor = interest_rate.mul_u64(now - last_updated);
let interest_accumulated = self.debt.mul(simple_interest_factor);
self.debt = self.debt.add(interest_accumulated);
```

Individual obligation debt accrual in `debt.move:22-26` calculates:

```move
public(package) fun debt(self: &Debt, borrow_index: Decimal): Decimal {
    if (borrow_index.eq(self.borrow_index)) { return self.amount };
    self.amount.mul(borrow_index).div(self.borrow_index)
}
```

Both use WAD-precision (10^18) fixed-point arithmetic, but the rounding occurs at different granularities:
- **Reserve**: `total_debt * interest_factor` — one multiplication with truncation
- **Obligation**: `amount * new_index / old_index` — two operations (mul then div), each with truncation

Because each obligation's debt computation independently truncates, `sum(individual_debts) < reserve.debt`. The gap grows with:
- Number of borrowers (more independent truncations)
- Frequency of accrual (more rounding events)
- Time duration (cumulative effect)

This phantom debt inflates the exchange rate via `exchange_rate = (cash + debt - cash_reserve) / total_supply` (reserve.move:97-100), giving depositors a slightly higher rate than is actually collectible. When the last borrowers repay their debts fully, a residual `reserve.debt > 0` persists that no obligation owes.

The `repay_amount` function (reserve.move:203-217) has an overpayment path that handles `debt.lt(repay_amount)`, but this only works for the final repayer — if there are multiple remaining borrowers, each can only repay their own individual debt, and the phantom delta accumulates.

## Impact

Over the protocol's lifetime, the exchange rate is systematically inflated by the phantom debt. Depositors see a higher exchange rate than warranted by actual collectible debts. The protocol cannot fully close out a market's debt: after all borrowers repay, a residual debt balance remains in the reserve that is owed by no one. While the per-accrual loss is small (< 1 WAD unit per obligation per accrual), it compounds over thousands of accrual events and hundreds of borrowers.

## Code Snippet

- reserve.move:139-142 (reserve-level debt accrual)
- debt.move:22-26 (obligation-level debt calculation)
- reserve.move:97-100 (exchange rate using `debt`)

## Tool used

Manual Review + Automated Analysis

## Recommendation

Periodically reconcile `reserve.debt` against the sum of individual obligation debts, or use a "debt shares" model (similar to ERC-4626 vault shares) where obligations hold shares of the total debt rather than individual amounts:

```move
// Debt shares model:
// obligation.debt_shares = shares
// total_debt = reserve.debt
// individual_debt = obligation.debt_shares * reserve.debt / total_debt_shares
// This eliminates per-obligation rounding divergence
```

Alternatively, accept the divergence and add a `dust_cleanup` admin function to zero out residual phantom debt when no obligations exist for a market.
