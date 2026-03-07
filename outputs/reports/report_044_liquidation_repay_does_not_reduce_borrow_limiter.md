## Title
Liquidation Repay Path Does Not Reduce Borrow Rate-Limiter Usage

## Summary
The borrow rate limiter usage is increased on `borrow` and reduced on `repay`, but liquidation-driven debt repayment does not call limiter reduction at all. As a result, successful liquidations can reduce real debt while limiter usage remains elevated, causing new borrows to be blocked until the time window expires.

## Vulnerability Detail
`handle_borrow` increments the borrow limiter via `add_outflow(now, borrow_amount)`, and `handle_repay` explicitly reduces limiter usage via `reduce_outflow(now, coin.value())` after repayment.

However, `liquidation_inner` also repays debt into the same reserve (`debt_reserve.repay_amount(...)`) but does not reduce borrow limiter usage for the repaid amount. The function even documents `// NOTE: disable rate limit` in this path, and no borrow-limiter reconciliation is performed before returning.

This creates state divergence between:
- Economic state: debt is repaid (partially/fully) by liquidation
- Limiter state: borrow outflow usage is not reduced accordingly

Therefore, after large or repeated liquidations, the limiter can remain artificially saturated and reject legitimate new borrows (`add_outflow` checks), despite debt being materially reduced.

## Impact
Borrow capacity can remain incorrectly constrained after liquidation events, especially during volatile periods where liquidations are frequent. This can cause protocol-level borrowing DoS (false-positive limiter exhaustion), reduce market utilization, and delay normal market recovery even when debt has already been repaid.

## Code Snippet (file:line)
- `contracts/protocol/sources/internal/market/market.move:402`  
  `emode.borrow_mut_borrow_limiter().add_outflow(now, borrow_amount);`
- `contracts/protocol/sources/internal/market/market.move:483`  
  `emode.borrow_mut_borrow_limiter().reduce_outflow(now, coin.value());`
- `contracts/protocol/sources/internal/market/market.move:745`  
  `// NOTE: disable rate limit`
- `contracts/protocol/sources/internal/market/market.move:786`  
  `debt_reserve.repay_amount<MarketType, DebtType>(available_repay_coin);`

## Tool used
Manual Review + Automated Analysis

## Recommendation
When liquidation repays debt, reduce borrow-limiter usage by the actual repaid amount (excluding refunded debt coin), aligned with the `repay` path semantics. If liquidation is intentionally excluded from limiter accounting, introduce explicit compensating logic so borrow limiter usage still tracks net debt outflow/inflow consistently.
