### Query functions return stale reserve data without accruing interest first

### Summary

`obligation_query::get_obligation_detail` and `market_query::get_asset_detail` read reserve data (borrow index, utilization rate, debt amounts) without first accruing interest, causing the returned values to be outdated by up to the time since the last protocol interaction.

### Root Cause

In [`obligation_query.move:64`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/query/obligation_query.move#L64), the borrow index is read directly without accruing interest:

```move
let market_borrow_index = market.reserve_by_type(debt_type).borrow_index().value();
```

Similarly in [`market_query.move:68-69`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/query/market_query.move#L68-L69):

```move
let interest_rate = asset.interest_model().calc_interest(reserve.util_rate());
let borrow_index = reserve.calculate_borrow_index<MarketType>(interest_rate, now);
```

`market_query` does calculate what the borrow index WOULD be (via `calculate_borrow_index`), but `obligation_query` uses the STORED index directly. Both functions don't accrue interest to the reserve, so `util_rate()`, `exchange_rate()`, and `protocol_reserve()` are all stale.

### Internal Pre-conditions

1. Time needs to pass since the last protocol interaction (deposit/withdraw/borrow/repay) on the queried asset.

### External Pre-conditions

None.

### Attack Path

No direct attack — this is an information accuracy issue. Off-chain systems (liquidation bots, UIs, indexers) that rely on query functions may make incorrect decisions based on stale data:

1. Liquidation bot queries `get_obligation_detail` to check if a position is liquidatable.
2. The query returns stale debt (lower than actual), making the position appear healthier.
3. Bot decides NOT to liquidate.
4. Position is actually underwater and accumulates bad debt.

### Impact

Off-chain systems using query functions may see debt amounts that are slightly lower than reality and utilization rates that are slightly outdated. For assets with high interest rates and infrequent interactions, the staleness could be significant. The `market_query` partially mitigates this by computing the theoretical borrow index, but the `obligation_query` does not.

### PoC

```
// obligation_query.move reads stored borrow_index:
//   let market_borrow_index = market.reserve_by_type(debt_type).borrow_index().value();
//   debt.debt(market_borrow_index).floor()  // uses stored index, not current
//
// If last interaction was 1 hour ago at 5% APY:
//   Stored index: 1.000000
//   Actual index: 1.000005707 (5% / 8760 hours)
//   For $1M debt: displayed = $1,000,000, actual = $1,000,005.71
//   Staleness: $5.71 (increases with time since last interaction)
```

### Mitigation

In `obligation_query::get_obligation_detail`, compute the theoretical borrow index the same way `market_query` does:

```move
let interest_rate = asset.interest_model().calc_interest(reserve.util_rate());
let market_borrow_index = reserve.calculate_borrow_index<MarketType>(interest_rate, clock_now(clock));
```
