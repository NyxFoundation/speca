# Liquidation Residual Overpayment Silently Consumed as Protocol Revenue

## Summary

In `liquidation_inner`, the return value of `unsafe_repay_debt_only` (the residual overpayment from ceiling rounding) is discarded via `let _residual = ...`. The full `available_repay_coin` — including the overpayment — is then deposited into the reserve via `repay_amount`, where the excess becomes `cash_reserve` (protocol revenue). Liquidators systematically lose small amounts on every liquidation.

## Vulnerability Detail

At `market.move:774`:

```move
let _residual = obligation.unsafe_repay_debt_only<MarketType, DebtType>(available_repay_coin.value());
```

`unsafe_repay_debt_only` (obligation.move:170-194) returns a residual when `available_repay_coin.value() > debt.unsafe_debt_amount().ceil()`. This residual represents overpayment due to ceiling rounding in earlier steps (lines 738-743 and 762-766 both use `.ceil()`).

The residual is bound to `_residual` and silently discarded. Then at line 787:

```move
debt_reserve.repay_amount<MarketType, DebtType>(available_repay_coin);
```

The FULL `available_repay_coin` is deposited. Inside `repay_amount` (reserve.move:203-217), if the repay amount exceeds the reserve's tracked debt, the excess goes to `cash_reserve`:

```move
if (self.debt.lt(repay_amount)) {
    let total_debt = self.debt.ceil();
    self.cash_reserve = self.cash_reserve.add_u64(coin.value() - total_debt);
    self.debt = math::float::zero();
}
```

The liquidator's overpayment silently becomes protocol revenue. The amount per liquidation is typically 1-2 units (from ceiling rounding), but across automated liquidation bots processing many liquidations, these losses accumulate.

## Internal Pre-conditions

1. Liquidation must trigger the ceiling-based refund calculation at lines 738-743 or 762-766.
2. The ceiling operation must produce a non-zero residual (i.e., the debt amount is not an exact integer).

## External Pre-conditions

None.

## Attack Path

1. Liquidator repays debt in a liquidation call.
2. Ceiling rounding at line 766 (`expected_repay_amount.ceil()`) or line 737 (`obligation_latest_borrow_amount.ceil()`) causes `available_repay_coin.value()` to be 1-2 units higher than the actual debt.
3. `unsafe_repay_debt_only` returns the excess as `_residual`, which is discarded.
4. `repay_amount` deposits the full coin including overpayment, routing excess to `cash_reserve`.
5. Liquidator loses the residual on every liquidation.

## Impact

Per-liquidation loss is typically 1-2 units (from ceiling rounding). For automated liquidation bots executing thousands of liquidations, the cumulative loss can become non-trivial. This is a fairness issue — liquidators are systematically overcharged, and the excess accrues to protocol revenue without explicit disclosure.

## Code Snippet

- `contracts/protocol/sources/internal/market/market.move:774` — `_residual` discarded
- `contracts/protocol/sources/internal/market/market.move:787` — full coin deposited via `repay_amount`
- `contracts/protocol/sources/internal/market/reserve.move:203-217` — excess routed to `cash_reserve`
- `contracts/protocol/sources/internal/market/obligation.move:170-194` — `unsafe_repay_debt_only` returns residual

## Related Findings

This finding compounds with two other liquidation-path issues:

- **report_036** (Liquidation Skips min_borrow_amount Check): Liquidation can leave dust positions below `min_borrow_amount`. When this happens, the ceiling-rounding residual described here is consumed by the protocol on the final liquidation that creates the dust — the borrower loses both the residual AND ends up with an economically unclearable position.
- **report_028** (Dust Obligations Unliquidatable): Once a dust position is created (via 036's missing check), if the position goes underwater, `seize_ctokens.floor()` returns 0 and the liquidation aborts. The residual loss from ceiling rounding (this report) has already been taken from the liquidator on the preceding liquidation that created the dust.

The three findings form a chain: 059 (over-charge on ceiling rounding) → 036 (dust position created) → 028 (dust position unliquidatable). Each is independently fixable but their compound effect is worse than any individual finding.

## Tool used

Manual Review

## Mitigation

Split the residual from the repay coin and return it to the liquidator:

```move
let residual = obligation.unsafe_repay_debt_only<MarketType, DebtType>(available_repay_coin.value());
if (residual > 0) {
    refund_coins.join(available_repay_coin.split(residual, ctx));
};
debt_reserve.repay_amount<MarketType, DebtType>(available_repay_coin);
```
