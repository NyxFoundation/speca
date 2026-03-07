# Full Repayment Rounding Overcharges Borrower by Up to 1 Unit

## Summary

When a borrower fully repays their debt, the obligation uses `ceil()` on the fractional debt amount, causing the borrower to pay up to 1 extra token unit. The excess goes to `cash_reserve` rather than being refunded.

## Vulnerability Detail

In `obligation.move:170-194`, full repayment uses `ceil()`:

```move
public(package) fun unsafe_repay_debt_only<MarketType, CoinType>(
    self: &mut Obligation<MarketType>,
    amount: u64,
): u64 {
    let debt = wit_table::borrow_mut(ObligationDebts {}, &mut self.debts, name);
    let debt_amount = debt.unsafe_debt_amount().ceil();  // Rounds UP

    let residual = if (debt_amount <= amount) {
        debt.cleared();
        amount - debt_amount  // Refund = payment - ceil(debt)
    } else {
        debt.unsafe_decrease(math::float::from(amount));
        0
    };
    residual
}
```

And in `reserve.move:203-217`:

```move
public(package) fun repay_amount<MarketType, CoinType>(self: &mut Reserve<MarketType>, coin: Coin<CoinType>) {
    let repay_amount = float::from(coin.value());
    if (self.debt.lt(repay_amount)) {
        let total_debt = self.debt.ceil();  // Also rounds UP
        self.cash_reserve = self.cash_reserve.add_u64(coin.value() - total_debt);
        // Excess = payment - ceil(debt) → less goes to reserve
        self.debt = math::float::zero();
    } else {
        self.debt = self.debt.sub(repay_amount);
    };
}
```

Both `ceil()` calls ensure the protocol never receives less than the true debt, but the borrower always pays at least `ceil(fractional_debt)`.

## Impact

- **Systematic overcharge**: Every full repayment overpays by up to 1 token unit
- **Dust accumulation**: Over many repayments, the protocol accumulates dust from rounding
- **Per-token severity varies**: 1 unit of BTC (1 satoshi) is negligible; 1 unit of a low-decimal token could be meaningful

Severity is Low as the overcharge is at most 1 unit per repayment.

## Code Snippet

- [`obligation.move:177`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/obligation.move#L177): `debt.unsafe_debt_amount().ceil()`
- [`reserve.move:209`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L209): `self.debt.ceil()`

## Tool used

Manual Review + Automated Analysis (Codex + Claude cross-validation)

## Recommendation

Document this as intended protocol-favoring rounding, or refund any overcharge to the borrower.
