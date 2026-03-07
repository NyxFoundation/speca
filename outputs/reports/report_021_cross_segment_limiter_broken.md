# Cross-Segment Rate Limiter Reduction is Broken

## Summary

The `reduce_outflow` function in the rate limiter only reduces usage in the current time segment. Outflow recorded in older segments within the sliding window is never reduced, meaning deposits/repayments that should free up rate limiter capacity only partially do so.

## Vulnerability Detail

In `limiter.move:100-119`, `reduce_outflow` finds the current segment and reduces its value:

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

The sliding window consists of multiple segments (e.g., 4 segments of 6 hours each for a 24-hour window). If a user withdrew 1000 tokens in segment 1 (6 hours ago) and then deposits 500 tokens back in the current segment (segment 2), `reduce_outflow` can only reduce segment 2's counter. The 1000 from segment 1 remains counted until that segment naturally expires.

Meanwhile, `count_current_outflow` (lines 55-77) sums ALL segments in the window:
```move
public(package) fun count_current_outflow(self: &Limiter, now: u64): u64 {
    // Sums values from all non-expired segments
    total = total + segment.value;
}
```

## Impact

- **Reduced capital efficiency**: Deposits/repayments don't free up rate limiter capacity for outflows recorded in earlier segments
- **False rate limit triggers**: Users may be blocked from withdrawing or borrowing even though net outflow has decreased due to inflows
- **Window-length dependency**: The effect worsens with longer sliding windows and more segments

## Code Snippet

- [`limiter.move:100-119`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/limiter.move#L100-L119): Current-segment-only reduction
- [`limiter.move:55-77`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/limiter.move#L55-L77): Cross-segment summation in `count_current_outflow`

## Tool used

Manual Review + Automated Analysis (Codex + Claude cross-validation)

## Recommendation

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
