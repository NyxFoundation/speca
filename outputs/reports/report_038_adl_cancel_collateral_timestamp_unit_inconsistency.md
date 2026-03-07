# ADL cancel_collateral_adl Emits Timestamp in Milliseconds Instead of Seconds

## Summary

The `cancel_collateral_adl` function emits the `time` field in milliseconds while all other ADL event emissions use seconds, causing off-chain indexers and monitoring systems to misinterpret the cancellation timestamp by a factor of 1000x.

## Vulnerability Detail

In `adl_admin.move`, there are four ADL event-emitting functions. Three of them consistently convert `clock.timestamp_ms()` to seconds by dividing by 1000:

```move
// enable_collateral_adl (line 100, 115):
let now = clock.timestamp_ms() / 1000;
// ...
time: now,  // SECONDS

// enable_debt_adl (line 164, 179):
let now = clock.timestamp_ms() / 1000;
// ...
time: now,  // SECONDS

// cancel_debt_adl (line 208):
time: clock.timestamp_ms() / 1000,  // SECONDS
```

However, `cancel_collateral_adl` (line 141) emits the raw millisecond value:

```move
// cancel_collateral_adl (line 141):
time: clock.timestamp_ms(),  // MILLISECONDS — BUG!
```

Both `cancel_collateral_adl` and `cancel_debt_adl` emit the same `ADLCancelEvent` struct, but with inconsistent time units. An off-chain system parsing these events uniformly would either:
- Interpret the collateral cancellation as occurring ~1000x in the future (if expecting seconds)
- Interpret all other ADL events as occurring ~1000x in the past (if expecting milliseconds)

## Impact

Off-chain monitoring and indexing systems that track ADL lifecycle events will misinterpret `cancel_collateral_adl` timestamps. This is particularly problematic for:
- ADL duration tracking (how long ADL was active before cancellation)
- Automated alerting systems that monitor ADL state transitions
- Historical analysis dashboards showing ADL activation/cancellation timelines

Since ADL is an emergency mechanism where timing is critical for risk assessment, incorrect timestamps in monitoring can delay human intervention or cause false alerts.

## Code Snippet

- `contracts/protocol/sources/entry_points/admin/adl.move:141` — `cancel_collateral_adl` uses `clock.timestamp_ms()` (milliseconds)
- `contracts/protocol/sources/entry_points/admin/adl.move:100` — `enable_collateral_adl` uses `clock.timestamp_ms() / 1000` (seconds)
- `contracts/protocol/sources/entry_points/admin/adl.move:164` — `enable_debt_adl` uses `clock.timestamp_ms() / 1000` (seconds)
- `contracts/protocol/sources/entry_points/admin/adl.move:208` — `cancel_debt_adl` uses `clock.timestamp_ms() / 1000` (seconds)

## Tool used

Manual Review + Automated Analysis

## Recommendation

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
