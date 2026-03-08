# Oracle Admin Event Uses Seconds While Delay Field and Protocol Admin Events Use Milliseconds

## Summary
`PriceDelayToleranceUpdated` emits `timestamp` in seconds (`timestamp_ms / 1000`) while the same event carries `delay_ms` in milliseconds and protocol admin events consistently emit `timestamp_ms` in milliseconds. This unit mismatch can corrupt off-chain monitoring and governance automation that consume admin events.

## Vulnerability Detail
In `x_oracle::oracle_admin::update_price_delay_tolerance_ms`, the emitted event is:
- `delay_ms`: millisecond unit
- `timestamp`: written as `clock.timestamp_ms() / 1000` (seconds)

This diverges from admin events in protocol modules (for example `protocol::market_admin`) that emit `timestamp_ms` directly via `clock::timestamp_ms(clock)`. A downstream indexer/automation normalizing admin events as milliseconds can mis-order or mis-time oracle risk-control changes by 1000x.

## Internal Pre-conditions
1. Admin must call update_price_delay_tolerance_ms on x_oracle.

## External Pre-conditions
None.

## Attack Path
1. Admin updates oracle price delay tolerance via update_price_delay_tolerance_ms.
2. PriceDelayToleranceUpdated event emits timestamp = clock.timestamp_ms() / 1000 (seconds).
3. Off-chain indexer consuming protocol admin events expects timestamp_ms (milliseconds).
4. Indexer interprets oracle config change time as ~1000x earlier than actual.
5. Incident timeline and automated guardrails display incorrect parameter change timing.

## Impact
Operational security tooling can misinterpret when oracle delay tolerance was changed, causing delayed alerts, incorrect incident timelines, and faulty automated guardrails that depend on accurate parameter-change timing.

## Code Snippet (file:line)
- `contracts/x_oracle/sources/entry_points/admin.move:48`
- `contracts/protocol/sources/entry_points/admin/market.move:69`
- `contracts/protocol/sources/entry_points/admin/market.move:96`

## Tool used
Manual Review + Automated Analysis

## Mitigation
Standardize admin-event time units across modules. Prefer explicit `timestamp_ms` naming and emit raw `clock::timestamp_ms(clock)` for oracle admin events as well, or clearly version/document event schema and enforce unit-aware parsing in indexers.
