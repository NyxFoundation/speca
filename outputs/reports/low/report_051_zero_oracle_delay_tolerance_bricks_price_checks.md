### Zero `price_delay_tolerance_ms` Configuration Can Brick Oracle Reads and Lending Flows

Admin will cause a DoS on all price-dependent lending flows for all protocol users

### Summary

The missing lower-bound validation in `update_price_delay_tolerance_ms` (only enforces an upper bound) will cause a denial-of-service on all price-dependent lending flows for all protocol users as the admin setting `price_delay_tolerance_ms` to `0` will make `check_price` require `age <= 0`, causing all oracle reads via `get_price` / `get_price_with_check` to revert as stale.

### Root Cause

In [`contracts/x_oracle/sources/internal/x_oracle.move:148-150`](contracts/x_oracle/sources/internal/x_oracle.move#L148-L150) the `update_price_delay_tolerance_ms` function only checks the upper bound (`<= MAX_DELAY_TOLERANCE_MS`) and stores the value without enforcing a minimum, allowing `price_delay_tolerance_ms = 0`:

```move
// Only upper bound checked — zero is accepted
assert!(price_delay_tolerance_ms <= MAX_DELAY_TOLERANCE_MS, oracle_error::invalid_delay_tolerance());
self.price_delay_tolerance_ms = price_delay_tolerance_ms;
```

In the oracle read path at [`contracts/x_oracle/sources/entry_points/user.move:66-67`](contracts/x_oracle/sources/entry_points/user.move#L66-L67), staleness is computed as `age = clock.timestamp_ms() - last_updated * 1000` and asserted `age <= price_delay_tolerance_ms`. With tolerance of zero, any non-zero age fails, bricking all oracle reads and downstream safety checks in [`contracts/protocol/sources/internal/market/market.move:1197-1199`](contracts/protocol/sources/internal/market/market.move#L1197-L1199) and [`market.move:1283-1285`](contracts/protocol/sources/internal/market/market.move#L1283-L1285).

### Internal Pre-conditions

1. [Admin needs to call `update_price_delay_tolerance_ms` to set] `price_delay_tolerance_ms` to exactly `0` (no lower bound check prevents this).

### External Pre-conditions

None.

### Attack Path

1. Admin calls `update_price_delay_tolerance_ms` with value `0` (misconfiguration).
2. Oracle read path computes `age = clock.timestamp_ms() - last_updated * 1000`.
3. `check_price` asserts `age <= 0`, which fails for any non-zero age.
4. All `get_price` / `get_price_with_check` calls revert.
5. Borrow/withdraw safety checks (which require oracle prices) all fail.
6. Price-dependent lending flows are blocked until admin corrects the tolerance.

### Impact

The protocol users suffer a complete denial-of-service on all price-dependent lending flows (borrow, withdraw, and health-check-based operations) until the admin corrects the misconfiguration.

### PoC

_No PoC provided._

### Mitigation

Reject zero tolerance at configuration time by adding a lower bound check:

```move
public(package) fun update_price_delay_tolerance_ms(self: &mut XOracle, price_delay_tolerance_ms: u64) {
    assert!(price_delay_tolerance_ms > 0, oracle_error::invalid_delay_tolerance());
    assert!(price_delay_tolerance_ms <= MAX_DELAY_TOLERANCE_MS, oracle_error::invalid_delay_tolerance());
    self.price_delay_tolerance_ms = price_delay_tolerance_ms;
}
```

Optionally enforce a non-trivial minimum (e.g. `>= 1000ms`) to avoid accidental near-zero configurations.
