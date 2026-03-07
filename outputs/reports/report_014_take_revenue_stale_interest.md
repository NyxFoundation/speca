# take_revenue Does Not Accrue Interest Before Withdrawal

## Summary

The admin `take_revenue` entry point withdraws accumulated protocol revenue from reserves without first calling `accrue_interest()`. This means any interest earned since the last user interaction is not reflected in `cash_reserve`, causing the protocol to systematically under-collect revenue.

## Vulnerability Detail

In `revenue.move:23-49`, the `take_revenue` function directly calls `market::take_revenue` without triggering interest accrual:

```move
public fun take_revenue<MarketType, CoinType>(
    _: &AdminCap,
    self: &ProtocolApp,
    market: &mut Market<MarketType>,
    amount: u64,
    recipient: address,
    clock: &Clock,
    ctx: &mut TxContext,
) {
    // ... validation checks ...
    // NO call to accrue_interest() here
    let coin = market::take_revenue<MarketType, CoinType>(market, amount, ctx);
    transfer::public_transfer(coin, recipient);
}
```

The `cash_reserve` field that tracks protocol revenue is only updated during `accrue_interest()` (reserve.move:143):
```move
self.cash_reserve = self.cash_reserve.add(reserve_factor.mul(interest_accumulated));
```

If no user interaction (borrow, repay, deposit, withdraw) has occurred since the last accrual, the `cash_reserve` is stale. The admin either:
1. Takes less revenue than actually available (under-collection), or
2. Is forced to trigger a user operation first to refresh accrual (operational burden).

## Impact

Protocol revenue leakage. In low-activity markets or during periods of no user interaction, significant interest can accumulate without being reflected in `cash_reserve`. The admin cannot efficiently collect all earned revenue in a single transaction. Over time, this compounds as uncollected revenue is effectively donated to depositors via an inflated exchange rate.

## Code Snippet

- [`revenue.move:23-49`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/entry_points/admin/revenue.move#L23-L49): No `accrue_interest` call
- [`reserve.move:143`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L143): `cash_reserve` only updated during accrual

## Tool used

Manual Review + Automated Analysis (Codex + Claude cross-validation)

## Recommendation

Call `accrue_interest` before taking revenue:

```move
public fun take_revenue<MarketType, CoinType>(..., clock: &Clock, ...) {
    let now = clock::timestamp_ms(clock) / 1000;
    market.accrue_interest_for_asset<CoinType>(now);  // Refresh first
    let coin = market::take_revenue<MarketType, CoinType>(market, amount, ctx);
    transfer::public_transfer(coin, recipient);
}
```
