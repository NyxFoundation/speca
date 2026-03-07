# Pyth Adapter Startup Underflow DoS Window

## Summary

The Pyth oracle adapter may underflow during the startup period when `timestamp_ms` from the Pyth price feed is zero or very small, causing arithmetic underflow in staleness checks and reverting all operations that depend on oracle prices.

## Vulnerability Detail

When a Pyth price feed is first initialized or hasn't received its first update, the `timestamp` field may be 0 or a very old value. The staleness check computes:

```move
let elapsed = now - price_timestamp;  // Underflows if price_timestamp > now (unlikely)
// Or more commonly:
assert!(price_timestamp >= now - staleness_threshold, ...);
// Reverts if price_timestamp is 0 and now is large
```

During the startup window:
1. Market is created and configured with a Pyth price feed
2. First Pyth price update hasn't arrived yet
3. All user operations (deposit, borrow, withdraw, repay, liquidate) call `get_price` which reads the stale/zero timestamp
4. Staleness check fails, reverting all operations

This creates a denial-of-service window between market creation and first oracle update.

## Impact

- **Temporary DoS**: All market operations blocked until the first oracle update
- **Initialization ordering**: If markets are created during low-activity periods (weekends, holidays), the DoS window can be extended
- **No fallback**: There is no alternative price source or graceful degradation

Severity is Low as this is a temporary startup condition, but it affects protocol availability.

## Code Snippet

- Oracle staleness check in user.move price retrieval functions

## Tool used

Manual Review + Automated Analysis (Codex)

## Recommendation

Initialize markets with a valid initial price or require the first oracle update before enabling user operations:

```move
public fun initialize_market_with_price<MarketType, CoinType>(
    _: &AdminCap,
    initial_price: u64,  // Admin-provided initial price
    // ...
) {
    // Set initial price with current timestamp
    // Enable operations only after first real oracle update
}
```
