### `cancel_collateral_adl` will emit incorrect timestamp causing off-chain indexers to misinterpret ADL cancellation timing by 1000x

### Summary

Inconsistent timestamp unit in `cancel_collateral_adl` (milliseconds instead of seconds) will cause incorrect ADL lifecycle tracking for off-chain monitoring systems as the function will emit `ADLCancelEvent` with a `time` field 1000x larger than all other ADL events.

### Root Cause

In [`adl.move:141`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/admin/adl.move#L141) `cancel_collateral_adl` emits the raw millisecond value while all other ADL functions divide by 1000:

```move
// cancel_collateral_adl (line 141):
time: clock.timestamp_ms(),  // MILLISECONDS — BUG!
```

All three other ADL event-emitting functions consistently convert to seconds:

```move
// enable_collateral_adl (line 100, 115):
let now = clock.timestamp_ms() / 1000;
time: now,  // SECONDS

// enable_debt_adl (line 164, 179):
let now = clock.timestamp_ms() / 1000;
time: now,  // SECONDS

// cancel_debt_adl (line 208):
time: clock.timestamp_ms() / 1000,  // SECONDS
```

Both `cancel_collateral_adl` and `cancel_debt_adl` emit the same `ADLCancelEvent` struct, but with inconsistent time units.

### Internal Pre-conditions

1. [Admin needs to call `enable_collateral_adl` to set] ADL collateral mode to be exactly active, and then call `cancel_collateral_adl` to cancel it.

### External Pre-conditions

None.

### Attack Path

1. Admin activates collateral ADL via `enable_collateral_adl` (emits timestamp in seconds).
2. Admin later cancels collateral ADL by calling `cancel_collateral_adl`.
3. `ADLCancelEvent` emits `time = clock.timestamp_ms()` (milliseconds, not divided by 1000).
4. Off-chain indexer parsing all ADL events uniformly as seconds interprets the cancellation as occurring ~1000x in the future.
5. Monitoring dashboard shows incorrect ADL duration and cancellation timing.

### Impact

The off-chain monitoring and indexing systems suffer incorrect ADL lifecycle tracking. Since ADL is an emergency mechanism where timing is critical for risk assessment, incorrect timestamps in monitoring can delay human intervention or cause false alerts. ADL duration tracking, automated alerting systems, and historical analysis dashboards will all misinterpret `cancel_collateral_adl` timestamps.

### PoC

_No PoC provided._

### Mitigation

Divide by 1000 to match the convention used by all other ADL events:

```move
// In cancel_collateral_adl, line 141:
emit(ADLCancelEvent {
    market: market_type,
    coin: std::type_name::with_defining_ids<CoinType>(),
    is_borrow: false,
    emode_group_id: none(),
    time: clock.timestamp_ms() / 1000,  // Fix: use seconds like all other ADL events
    operator: ctx.sender(),
});
```
