### Protocol will systematically extract rounding-based overpayments from liquidators on every liquidation

### Summary

The discarded residual return value from `unsafe_repay_debt_only` (bound to `_residual` and ignored) will cause systematic small losses for liquidators as the protocol depositing the full `available_repay_coin` (including the ceiling-rounding overpayment) into the reserve will route the excess to `cash_reserve` as protocol revenue.

### Root Cause

In [`contracts/protocol/sources/internal/market/market.move:774`](contracts/protocol/sources/internal/market/market.move#L774) the residual from `unsafe_repay_debt_only` is discarded:

```move
let _residual = obligation.unsafe_repay_debt_only<MarketType, DebtType>(available_repay_coin.value());
```

Then at [`contracts/protocol/sources/internal/market/market.move:787`](contracts/protocol/sources/internal/market/market.move#L787) the full coin (including overpayment) is deposited:

```move
debt_reserve.repay_amount<MarketType, DebtType>(available_repay_coin);
```

Inside `repay_amount` at [`contracts/protocol/sources/internal/market/reserve.move:203-217`](contracts/protocol/sources/internal/market/reserve.move#L203-L217), when the repay amount exceeds the reserve's tracked debt, the excess goes to `cash_reserve`:

```move
if (self.debt.lt(repay_amount)) {
    let total_debt = self.debt.ceil();
    self.cash_reserve = self.cash_reserve.add_u64(coin.value() - total_debt);
    self.debt = math::float::zero();
}
```

The overpayment originates from ceiling rounding at lines 738-743 and 762-766 (both use `.ceil()`), and `unsafe_repay_debt_only` at [`contracts/protocol/sources/internal/market/obligation.move:170-194`](contracts/protocol/sources/internal/market/obligation.move#L170-L194) returns this residual, which is then silently consumed.

### Internal Pre-conditions

1. [Liquidation needs to trigger the ceiling-based refund calculation to make] the ceiling operation produce a non-zero residual (i.e., the debt amount is not an exact integer).

### External Pre-conditions

None.

### Attack Path

1. Liquidator repays debt in a liquidation call.
2. Ceiling rounding at line 766 (`expected_repay_amount.ceil()`) or line 737 (`obligation_latest_borrow_amount.ceil()`) causes `available_repay_coin.value()` to be 1-2 units higher than the actual debt.
3. `unsafe_repay_debt_only` returns the excess as `_residual`, which is discarded.
4. `repay_amount` deposits the full coin including overpayment, routing excess to `cash_reserve`.
5. Liquidator loses the residual on every liquidation.

### Impact

The liquidators suffer an approximate loss of 1-2 token units per liquidation due to ceiling rounding. For automated liquidation bots executing thousands of liquidations, the cumulative loss becomes non-trivial. The protocol gains systematic undisclosed revenue from these overpayments.

### PoC

_No PoC provided._

### Mitigation

Split the residual from the repay coin and return it to the liquidator:

```move
let residual = obligation.unsafe_repay_debt_only<MarketType, DebtType>(available_repay_coin.value());
if (residual > 0) {
    refund_coins.join(available_repay_coin.split(residual, ctx));
};
debt_reserve.repay_amount<MarketType, DebtType>(available_repay_coin);
```
