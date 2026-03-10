### Users will be falsely blocked from withdrawals due to rate limiter not freeing capacity across segments

### Summary

`reduce_outflow` only reducing usage in the current time segment will cause false rate limit triggers for users as deposits and repayments that should free up rate limiter capacity will fail to reduce outflow recorded in older segments within the sliding window

### Root Cause

In [`limiter.move:100-119`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/limiter.move#L100-L119) the `reduce_outflow` function only reduces the current segment's value:

```move
public(package) fun reduce_outflow(
    limiter: &mut Limiter,
    now: u64,
    value: u64,
) {
    let (_, current_segment_start) = limiter.current_segment_window(now);
    let i = 0;
    while (i < limiter.segments.length()) {
        let segment = limiter.segments.borrow_mut(i);
        if (segment.timestamp == current_segment_start) {
            // Only reduces in current segment, saturating at zero
            if (segment.value <= value) {
                segment.value = 0;
            } else {
                segment.value = segment.value - value;
            };
            return
        };
        i = i + 1;
    };
}
```

Meanwhile, `count_current_outflow` ([`limiter.move:55-77`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/limiter.move#L55-L77)) sums ALL segments in the window:

```move
public(package) fun count_current_outflow(self: &Limiter, now: u64): u64 {
    // Sums values from all non-expired segments
    total = total + segment.value;
}
```

The sliding window consists of multiple segments (e.g., 4 segments of 6 hours each for a 24-hour window). If a user withdrew 1000 tokens in segment 1 and then deposits 500 tokens back in segment 2, `reduce_outflow` can only reduce segment 2's counter. The 1000 from segment 1 remains counted until that segment naturally expires.

### Internal Pre-conditions

1. [The rate limiter needs to be configured to set] the sliding window to have multiple segments.
2. [A user needs to have withdrawn or borrowed to set] outflow recorded in an earlier (non-current) segment.

### External Pre-conditions

None.

### Attack Path

1. User withdraws 1000 tokens in segment 1 (6 hours ago), recorded in limiter.
2. User deposits 500 tokens back in current segment 2.
3. `reduce_outflow` only reduces segment 2's counter (which may be 0).
4. `count_current_outflow` still sums 1000 from segment 1, limiting further withdrawals.
5. Effective rate limit capacity is not freed by the deposit.

### Impact

The users suffer reduced capital efficiency as deposits and repayments do not free up rate limiter capacity for outflows recorded in earlier segments. Users may be blocked from withdrawing or borrowing even though net outflow has decreased due to inflows. The effect worsens with longer sliding windows and more segments. This occurs naturally as time passes across segment boundaries -- any user who borrows in segment N and repays in segment N+1 experiences reduced limiter efficiency.

### PoC

_No PoC provided._

### Mitigation

Allow `reduce_outflow` to reduce across segments, starting from the oldest:

```move
public(package) fun reduce_outflow(limiter: &mut Limiter, now: u64, value: u64) {
    let remaining = value;
    let i = 0;
    while (i < limiter.segments.length() && remaining > 0) {
        let segment = limiter.segments.borrow_mut(i);
        if (!is_expired(segment, now)) {
            let reduction = math::min(segment.value, remaining);
            segment.value = segment.value - reduction;
            remaining = remaining - reduction;
        };
        i = i + 1;
    };
}
```
