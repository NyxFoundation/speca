### take_revenue Does Not Accrue Interest Before Withdrawal

Admin will under-collect protocol revenue from reserves

### Summary

Missing `accrue_interest` call in `take_revenue` will cause an under-collection of protocol revenue for the protocol as the admin will withdraw from a stale `cash_reserve` that does not reflect interest earned since the last user interaction

### Root Cause

In [`revenue.move:23-49`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/entry_points/admin/revenue.move#L23-L49) the `take_revenue` function directly calls `market::take_revenue` without triggering interest accrual:

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

The `cash_reserve` field that tracks protocol revenue is only updated during `accrue_interest()` ([`reserve.move:143`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L143)):

```move
self.cash_reserve = self.cash_reserve.add(reserve_factor.mul(interest_accumulated));
```

If no user interaction (borrow, repay, deposit, withdraw) has occurred since the last accrual, the `cash_reserve` is stale and the admin receives less revenue than actually available.

### Internal Pre-conditions

1. [Borrowers need to have outstanding borrows to set] the reserve to have active interest generation.
2. [No user needs to interact with the reserve to set] time elapsed since last user interaction (borrow/repay/deposit/withdraw) on the asset.

### External Pre-conditions

None.

### Attack Path

1. Interest accrues on outstanding borrows but no user interactions trigger `accrue_interest()`.
2. Admin calls `take_revenue` to collect protocol revenue.
3. `cash_reserve` reflects stale value from last accrual, not current earned interest.
4. Admin receives less revenue than actually available.

### Impact

The protocol suffers an under-collection of revenue. In low-activity markets or during periods of no user interaction, significant interest can accumulate without being reflected in `cash_reserve`. The admin cannot efficiently collect all earned revenue in a single transaction. Over time, this compounds as uncollected revenue is effectively donated to depositors via an inflated exchange rate.

### PoC

_No PoC provided._

### Mitigation

Call `accrue_interest` before taking revenue:

```move
public fun take_revenue<MarketType, CoinType>(..., clock: &Clock, ...) {
    let now = clock::timestamp_ms(clock) / 1000;
    market.accrue_interest_for_asset<CoinType>(now);  // Refresh first
    let coin = market::take_revenue<MarketType, CoinType>(market, amount, ctx);
    transfer::public_transfer(coin, recipient);
}
```
