## Title (English)
Zero `price_delay_tolerance_ms` Configuration Can Brick Oracle Reads and Lending Flows

## Summary
`x_oracle::update_price_delay_tolerance_ms` allows setting delay tolerance to `0`, because it only enforces an upper bound. With `0` tolerance, `check_price` requires `age <= 0`, so almost all reads via `get_price` / `get_price_with_check` revert as stale, which propagates into core borrow/withdraw safety checks.

## Vulnerability Detail
The admin path allows `price_delay_tolerance_ms = 0`:
- `x_oracle::x_oracle::update_price_delay_tolerance_ms` checks only `<= MAX_DELAY_TOLERANCE_MS` and then stores the value.

Oracle read path computes staleness as:
- `age = clock.timestamp_ms() - last_updated * 1000`
- `assert!(age <= price_delay_tolerance_ms, oracle_stale_price_error)`

If tolerance is zero, any non-zero age fails. Since timestamps are sampled at runtime and oracle update time is second-based, this effectively makes `get_price`/`get_price_with_check` fail in normal operation.

This directly affects protocol execution paths that require oracle prices, e.g. `debts_value_usd_non_liquidation` and `collaterals_usd_non_liquidation` in `market.move`, which are used by obligation safety checks for borrow/withdraw paths.

## Impact
A single admin misconfiguration (`delay_tolerance_ms = 0`) can cause a protocol-wide DoS on price-dependent lending flows (borrow/withdraw and other health-check-based operations), because oracle reads revert with stale-price errors.

## Code Snippet (file:line)
- `contracts/x_oracle/sources/internal/x_oracle.move:148-150`
- `contracts/x_oracle/sources/entry_points/user.move:66-67`
- `contracts/protocol/sources/internal/market/market.move:1197-1199`
- `contracts/protocol/sources/internal/market/market.move:1283-1285`

## Tool used
Manual Review + Automated Analysis

## Recommendation
Reject zero tolerance at configuration time by adding a lower bound check:

```move
public(package) fun update_price_delay_tolerance_ms(self: &mut XOracle, price_delay_tolerance_ms: u64) {
    assert!(price_delay_tolerance_ms > 0, oracle_error::invalid_delay_tolerance());
    assert!(price_delay_tolerance_ms <= MAX_DELAY_TOLERANCE_MS, oracle_error::invalid_delay_tolerance());
    self.price_delay_tolerance_ms = price_delay_tolerance_ms;
}
```

Optionally enforce a non-trivial minimum (e.g. `>= 1000ms`) to avoid accidental near-zero configurations.
