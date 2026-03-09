# Liquidation Repay Path Does Not Reduce Borrow Rate-Limiter Usage

## Summary
The borrow rate limiter usage is increased on `borrow` and reduced on `repay`, but liquidation-driven debt repayment does not call limiter reduction at all. As a result, successful liquidations can reduce real debt while limiter usage remains elevated, causing new borrows to be blocked until the time window expires.

## Vulnerability Detail
`handle_borrow` increments the borrow limiter via `add_outflow(now, borrow_amount)`, and `handle_repay` explicitly reduces limiter usage via `reduce_outflow(now, coin.value())` after repayment.

However, `liquidation_inner` also repays debt into the same reserve (`debt_reserve.repay_amount(...)`) but does not reduce borrow limiter usage for the repaid amount. The function explicitly documents `// NOTE: disable rate limit` (market.move:745) in this path, and no borrow-limiter reconciliation is performed before returning.

**Note on intentional design**: The `// NOTE: disable rate limit` comment suggests the developers may have intentionally excluded liquidation from limiter accounting. However, the resulting state divergence between economic debt levels and limiter usage still creates a functional issue: the limiter becomes artificially saturated after liquidation events, blocking legitimate new borrows even though debt has been reduced. The limiter does self-recover over its time window, but during volatile periods this can compound — exactly when new borrowing is most needed for market efficiency.

This creates state divergence between:
- Economic state: debt is repaid (partially/fully) by liquidation
- Limiter state: borrow outflow usage is not reduced accordingly

Therefore, after large or repeated liquidations, the limiter can remain artificially saturated and reject legitimate new borrows (`add_outflow` checks), despite debt being materially reduced.

## Internal Pre-conditions

1. Borrow rate limiter must be active for the eMode group.
2. Borrow outflow must have been recorded in the limiter.

## External Pre-conditions

1. Market conditions must trigger liquidations, which repay debt into the reserve.

## Attack Path

1. Borrow limiter tracks 900/1000 capacity used.
2. Price drop triggers liquidation of multiple obligations, repaying 500 units of debt.
3. liquidation_inner calls debt_reserve.repay_amount but does NOT call reduce_outflow on borrow limiter.
4. Limiter still shows 900/1000 used despite 500 debt reduction.
5. New legitimate borrows are blocked (limiter reports capacity exhausted).
6. Limiter recovers only when time window expires naturally.

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

## Related Findings

This finding is one of three distinct rate limiter accounting issues:

- **report_058** (Repay Over-Reduces Borrow Limiter): The `handle_repay` path calls `reduce_outflow(coin.value())` with principal + accrued interest, but `add_outflow` only tracked the principal. This is the opposite direction — 058 *over-reduces* the limiter, while this report describes a path that *never reduces* at all. During market stress with both liquidations and repayments, these errors can partially offset (liquidation inflation minus repay over-reduction), but their magnitudes differ and neither cancels the other reliably.
- **report_021** (Cross-Segment Limiter Reduction is Broken): Even if liquidation were to call `reduce_outflow`, the cross-segment design flaw means the reduction would only apply to the current segment. If the original borrow was in an earlier segment, the reduction would have no effect anyway.

## Tool used
Manual Review + Automated Analysis

## Mitigation
When liquidation repays debt, reduce borrow-limiter usage by the actual repaid amount (excluding refunded debt coin), aligned with the `repay` path semantics. If liquidation is intentionally excluded from limiter accounting, introduce explicit compensating logic so borrow limiter usage still tracks net debt outflow/inflow consistently.
