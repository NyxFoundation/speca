# Repay Reduces Borrow Rate Limiter by Interest-Inclusive Amount, Eroding Safety Margin

## Summary

`handle_repay` calls `reduce_outflow(now, coin.value())` using the full repayment coin value (principal + accrued interest), while `handle_borrow` calls `add_outflow(now, borrow_amount)` using only the principal. Over time, repayments systematically over-reduce the borrow rate limiter by the accrued interest delta, creating more borrow capacity than intended.

## Vulnerability Detail

In `market.move:402`, borrow adds outflow using the raw borrow amount:

```move
emode.borrow_mut_borrow_limiter().add_outflow(now, borrow_amount);
```

In `market.move:483`, repay reduces outflow using `coin.value()`:

```move
emode.borrow_mut_borrow_limiter().reduce_outflow(now, coin.value());
```

At this point `coin` has had the residual split off (line 475), so `coin.value()` equals the actual amount consumed by debt repayment. However, because `repay_debt` (called at line 469) first accrues interest on the obligation via `accrue_interest(borrow_index)`, the debt has grown. A full repayment of a 1000-unit borrow that accrued 50 units of interest requires 1050 units, and `reduce_outflow` is called with 1050 — while `add_outflow` was only called with 1000.

The `reduce_outflow` function (`limiter.move:100-119`) uses saturating subtraction on the current time segment:

```move
if (segment.value <= reduced_value) {
    segment.value = 0;
} else {
    segment.value = segment.value - reduced_value;
}
```

If the current segment contains outflows from multiple borrowers, the over-reduction (interest portion) eats into other borrowers' tracked outflow, effectively freeing phantom borrow capacity.

Example:
1. T1: User A borrows 1000 → segment += 1000
2. T2 (same segment): User B borrows 500 → segment = 1500
3. T2: User A repays 1050 (1000 principal + 50 interest) → segment = 1500 - 1050 = 450
4. B's tracked outflow was 500, but segment only shows 450 — 50 units of capacity have been freed

## Internal Pre-conditions

1. Interest must have accrued on the obligation's debt between borrow and repay.
2. Borrow and repay must fall within the same rate limiter segment (or the repay segment must contain other borrows' outflow).

## External Pre-conditions

None.

## Attack Path

1. Rate limiter is near capacity (e.g., 9500/10000 used).
2. Borrower A repays a long-held position where 500 units of interest have accrued.
3. `reduce_outflow` reduces current segment by 500 more than `add_outflow` originally added.
4. This frees 500 units of phantom capacity in the limiter.
5. New borrows can consume this phantom capacity, exceeding the intended rate limit.

## Impact

The borrow rate limiter's safety margin is eroded by the interest accrued between borrow and repay. In high-interest markets with frequent borrow-repay cycles, the cumulative over-reduction can create meaningful phantom capacity, allowing borrow volume to exceed the configured rate limit within a single cycle window. The magnitude scales with interest rates and time-between-operations.

## Code Snippet

- `contracts/protocol/sources/internal/market/market.move:402` — `add_outflow(now, borrow_amount)` uses principal only
- `contracts/protocol/sources/internal/market/market.move:483` — `reduce_outflow(now, coin.value())` uses principal + interest
- `contracts/protocol/sources/internal/market/limiter.move:100-119` — saturating subtraction on current segment

## Related Findings

This finding is one of three distinct rate limiter accounting issues, each affecting the same `Limiter` mechanism through a different path:

- **report_044** (Liquidation Repay Does Not Reduce Borrow Limiter): The liquidation path omits `reduce_outflow` entirely, causing the limiter to remain inflated after liquidations. This is the *opposite direction* — 044 under-reduces (by zero), while this report over-reduces (by the interest delta). Both distort the limiter's view of actual borrow outflow.
- **report_021** (Cross-Segment Limiter Reduction is Broken): `reduce_outflow` only operates on the current time segment. The over-reduction described here is further bounded by 021's bug — if the original borrow was in an earlier segment, the excess reduction can only eat into *current-segment* outflow, not the original segment. Conversely, 021 means that even the *correct* reduction amount may not fully apply.

Combined effect: Across a full limiter window, the net tracking error is `(interest delta from 058) - (missing liquidation reduction from 044) ± (cross-segment loss from 021)`. The three bugs partially cancel or compound depending on whether the market is in a repay-heavy or liquidation-heavy phase.

## Tool used

Manual Review

## Mitigation

Track the original borrow amount and use it for `reduce_outflow`, or cap the reduction to the principal portion:

```move
// Option 1: reduce by the original borrow amount, not the interest-inclusive repay
let original_borrow_amount = obligation_old_borrow_amount.sub(obligation_new_borrow_amount);
emode.borrow_mut_borrow_limiter().reduce_outflow(now, original_borrow_amount.ceil());

// Option 2: cap reduction to what was originally tracked
// (requires storing per-obligation borrow tracking in the limiter)
```
