### Borrowers will exceed the intended borrow rate limit due to interest-inclusive repay reduction, degrading the safety margin for all lenders

### Summary

The asymmetric accounting in `handle_repay` (calling `reduce_outflow` with the full principal + accrued interest amount while `handle_borrow` calls `add_outflow` with only the principal) will cause the borrow rate limiter's safety margin to erode for all lenders as borrowers repaying long-held positions will systematically over-reduce the limiter by the accrued interest delta, creating phantom borrow capacity.

### Root Cause

In [`contracts/protocol/sources/internal/market/market.move:402`](contracts/protocol/sources/internal/market/market.move#L402) borrow adds outflow using only the principal:

```move
emode.borrow_mut_borrow_limiter().add_outflow(now, borrow_amount);
```

But in [`contracts/protocol/sources/internal/market/market.move:483`](contracts/protocol/sources/internal/market/market.move#L483) repay reduces outflow using the full coin value (principal + accrued interest):

```move
emode.borrow_mut_borrow_limiter().reduce_outflow(now, coin.value());
```

Because `repay_debt` first accrues interest via `accrue_interest(borrow_index)`, a full repayment of a 1000-unit borrow that accrued 50 units of interest requires 1050 units, and `reduce_outflow` is called with 1050 while `add_outflow` was only called with 1000. The saturating subtraction in [`contracts/protocol/sources/internal/market/limiter.move:100-119`](contracts/protocol/sources/internal/market/limiter.move#L100-L119) eats into other borrowers' tracked outflow within the same segment:

```move
if (segment.value <= reduced_value) {
    segment.value = 0;
} else {
    segment.value = segment.value - reduced_value;
}
```

### Internal Pre-conditions

1. [Borrower needs to hold a position long enough for interest to accrue to set] the obligation's debt to be at least greater than the original borrow principal.
2. [Borrow and repay need to occur within the same rate limiter segment, or the repay segment needs to contain] other borrowers' outflow to be at least greater than `0`.

### External Pre-conditions

None.

### Attack Path

1. Rate limiter is near capacity (e.g., 9500/10000 used).
2. Borrower A repays a long-held position where 500 units of interest have accrued.
3. `reduce_outflow` reduces the current segment by 500 more than `add_outflow` originally added.
4. This frees 500 units of phantom capacity in the limiter.
5. New borrows can consume this phantom capacity, exceeding the intended rate limit.

### Impact

The lenders suffer eroded rate limiter safety margins. In high-interest markets with frequent borrow-repay cycles, the cumulative over-reduction creates meaningful phantom capacity, allowing borrow volume to exceed the configured rate limit within a single cycle window. The magnitude scales with interest rates and time-between-operations.

### PoC

_No PoC provided._

### Mitigation

Track the original borrow amount and use it for `reduce_outflow`, or cap the reduction to the principal portion:

```move
// Option 1: reduce by the original borrow amount, not the interest-inclusive repay
let original_borrow_amount = obligation_old_borrow_amount.sub(obligation_new_borrow_amount);
emode.borrow_mut_borrow_limiter().reduce_outflow(now, original_borrow_amount.ceil());

// Option 2: cap reduction to what was originally tracked
// (requires storing per-obligation borrow tracking in the limiter)
```
