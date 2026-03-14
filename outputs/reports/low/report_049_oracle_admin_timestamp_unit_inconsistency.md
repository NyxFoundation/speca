### Admin will corrupt off-chain monitoring and governance automation for the protocol operators due to oracle timestamp unit inconsistency

### Summary

The unit mismatch in `PriceDelayToleranceUpdated` event (emitting `timestamp` in seconds via `timestamp_ms / 1000` while the same event carries `delay_ms` in milliseconds and other protocol admin events consistently emit `timestamp_ms`) will cause corrupted off-chain monitoring and governance automation for protocol operators as the admin calling `update_price_delay_tolerance_ms` will emit an event whose timestamp is misinterpreted by 1000x by downstream indexers.

### Root Cause

In [`contracts/x_oracle/sources/entry_points/admin.move:48`](contracts/x_oracle/sources/entry_points/admin.move#L48) the `PriceDelayToleranceUpdated` event emits `timestamp` as `clock.timestamp_ms() / 1000` (seconds), diverging from protocol admin events in [`contracts/protocol/sources/entry_points/admin/market.move:69`](contracts/protocol/sources/entry_points/admin/market.move#L69) and [`market.move:96`](contracts/protocol/sources/entry_points/admin/market.move#L96) that emit `timestamp_ms` directly via `clock::timestamp_ms(clock)`:

```move
// x_oracle admin — emits seconds
timestamp: clock.timestamp_ms() / 1000

// protocol admin — emits milliseconds
timestamp_ms: clock::timestamp_ms(clock)
```

### Internal Pre-conditions

1. [Admin needs to call `update_price_delay_tolerance_ms` on `x_oracle` to trigger] the `PriceDelayToleranceUpdated` event emission with seconds-based timestamp.

### External Pre-conditions

None.

### Attack Path

1. Admin updates oracle price delay tolerance via `update_price_delay_tolerance_ms`.
2. `PriceDelayToleranceUpdated` event emits `timestamp = clock.timestamp_ms() / 1000` (seconds).
3. Off-chain indexer consuming protocol admin events expects `timestamp_ms` (milliseconds).
4. Indexer interprets the oracle config change time as ~1000x earlier than actual.
5. Incident timeline and automated guardrails display incorrect parameter change timing.

### Impact

The protocol operators suffer corrupted incident timelines and faulty automated guardrails due to 1000x timestamp misinterpretation, causing delayed alerts and incorrect audit trails for oracle parameter changes.

### PoC

_No PoC provided._

### Mitigation

Standardize admin-event time units across modules. Prefer explicit `timestamp_ms` naming and emit raw `clock::timestamp_ms(clock)` for oracle admin events as well, or clearly version/document event schema and enforce unit-aware parsing in indexers.
