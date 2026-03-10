### Liquidation-driven debt repayment will cause borrowing DoS for legitimate borrowers by leaving the borrow rate limiter artificially saturated

### Summary

Missing `reduce_outflow` call in the liquidation repay path will cause false-positive borrow limiter exhaustion for legitimate borrowers as cascading liquidations will repay debt without reducing limiter usage, blocking new borrows until the time window expires naturally.

### Root Cause

In [`market.move:745-786`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L745-L786) `liquidation_inner` repays debt into the reserve via `debt_reserve.repay_amount(...)` but does not call `reduce_outflow` on the borrow limiter. The function explicitly documents `// NOTE: disable rate limit` (line 745), and no borrow-limiter reconciliation is performed.

The normal borrow/repay paths correctly maintain limiter state:
```move
// handle_borrow (market.move:402):
emode.borrow_mut_borrow_limiter().add_outflow(now, borrow_amount);

// handle_repay (market.move:483):
emode.borrow_mut_borrow_limiter().reduce_outflow(now, coin.value());
```

But `liquidation_inner` (market.move:786) calls:
```move
debt_reserve.repay_amount<MarketType, DebtType>(available_repay_coin);
// No corresponding reduce_outflow call
```

This creates state divergence: economic debt is repaid by liquidation, but borrow outflow usage is not reduced accordingly.

### Internal Pre-conditions

1. [Admin needs to configure eMode group to set] borrow rate limiter to be active for the eMode group.
2. [Borrowers need to call `borrow` to cause] borrow outflow to be recorded in the limiter.

### External Pre-conditions

1. Market conditions must trigger liquidations (e.g., price drops causing undercollateralized positions).

### Attack Path

1. Borrow limiter tracks 900/1000 capacity used.
2. Price drop triggers liquidation of multiple obligations, repaying 500 units of debt.
3. `liquidation_inner` calls `debt_reserve.repay_amount` but does NOT call `reduce_outflow` on borrow limiter.
4. Limiter still shows 900/1000 used despite 500 debt reduction.
5. New legitimate borrowers call `borrow`, which calls `add_outflow` and is blocked (limiter reports capacity exhausted).
6. Limiter recovers only when the time window expires naturally.

### Impact

The legitimate borrowers suffer borrowing DoS during volatile periods. Borrow capacity remains incorrectly constrained after liquidation events, reducing market utilization and delaying normal market recovery even when debt has already been repaid. This is self-reinforcing: liquidations are most frequent during volatile periods, exactly when new borrowing is most needed for market efficiency.

### PoC

_No PoC provided._

### Mitigation

When liquidation repays debt, reduce borrow-limiter usage by the actual repaid amount (excluding refunded debt coin), aligned with the `repay` path semantics:

```move
// In liquidation_inner, after debt_reserve.repay_amount:
debt_reserve.repay_amount<MarketType, DebtType>(available_repay_coin);

// Add limiter reduction to match economic state
let debt_emode = self.emodes.load_mut(debt_emode_id);
debt_emode.borrow_mut_borrow_limiter().reduce_outflow(now, actual_repay_amount);
```

If liquidation is intentionally excluded from limiter accounting, introduce explicit compensating logic so borrow limiter usage still tracks net debt outflow/inflow consistently.
