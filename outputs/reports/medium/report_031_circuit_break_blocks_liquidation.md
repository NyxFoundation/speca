# Circuit Break Blocks Liquidation, Allowing Bad Debt Accumulation

## Summary

When the market's circuit breaker is triggered, all operations including liquidation are blocked. This prevents liquidators from closing underwater positions, allowing bad debt to accumulate unchecked during the circuit break period.

## Root Cause

In [`liquidate.move:59`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/lending/liquidate.move#L59), the `pre_liquidation_check` function unconditionally asserts that the circuit breaker has not been triggered via `assert!(!market.has_circuit_break_triggered(), protocol::error::market_under_circuit_break())`, which gates all three liquidation paths (normal, ADL borrow, ADL collateral) behind the circuit break check, preventing any liquidation during a circuit break period.

## Internal Pre-conditions

1. An admin must trigger the circuit breaker on the market via `trigger_circuit_break` at [`market.move:119-124`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/lending/market.move#L119-L124), setting the `CircuitBreakKey` dynamic field to `true`.
2. One or more borrower positions must be at or near their liquidation threshold at the time the circuit breaker is activated.

## External Pre-conditions

1. Collateral asset prices must decline during the circuit break period (e.g., continued market downturn or oracle price feed updates reflecting falling prices).

## Attack Path

1. Market experiences a price shock or oracle failure, prompting the admin to trigger the circuit breaker.
2. During the circuit break, collateral prices continue dropping.
3. Obligations that were marginally underwater become deeply underwater.
4. Liquidators attempt to call `liquidate` / `liquidate_as_coin` (line 177), `liquidate_adl_borrow` (line 224), or `liquidate_adl_deposit` (line 273), but all calls revert due to the `assert!(!market.has_circuit_break_triggered())` check in `pre_liquidation_check`.
5. No liquidation can occur to stem the bleeding during the entire circuit break period.
6. When the circuit break is lifted, a cascade of bad debt positions exists that may exceed protocol reserves.
7. If the bad debt exceeds the 101% threshold (line 985-992 of `market.move`), all close factor limits are bypassed, leading to a liquidation rush.

## Impact

- **Bad debt accumulation during emergencies**: The exact scenario where liquidation is most needed (market stress) is when it is blocked.
- **Cascading insolvency**: Positions that could have been safely liquidated during circuit break may become irreversibly insolvent.
- **Protocol loss socialization**: Bad debt must be absorbed by the protocol or socialized across depositors.

Severity is Medium because it requires admin action (triggering circuit break) and a concurrent market downturn, but the impact is systemic and can threaten protocol solvency.

## PoC

The `pre_liquidation_check` function in `liquidate.move:48-60` is called before every liquidation type:

```move
fun pre_liquidation_check<MarketType>(
    app: &ProtocolApp,
    cap: &PackageCallerCap,
    market: &Market<MarketType>,
    permission: u8,
) {
    app.validate_market<MarketType>(market);
    app.ensure_version_matches();
    app.ensure_has_permission(object::id(cap), permission);
    assert!(!market.has_circuit_break_triggered(), protocol::error::market_under_circuit_break());
}
```

All three liquidation paths are gated by this check:
- `liquidate` / `liquidate_as_coin` (line 177 via `pre_liquidation_check`)
- `liquidate_adl_borrow` (line 224)
- `liquidate_adl_deposit` (line 273)

The circuit breaker at `market.move:119-124` is a simple boolean that blocks all operations indiscriminately:

```move
public(package) fun trigger_circuit_break<MarketType>(self: &mut Market<MarketType>) {
    let is_circuit_break = dynamic_field::borrow_mut(&mut self.id, CircuitBreakKey {});
    assert!(!*is_circuit_break, error::already_under_circuit_break());
    *is_circuit_break = true;
}
```

This is the opposite of the desired behavior: circuit break should be a protective measure, but blocking liquidation actually amplifies systemic risk.

## Mitigation

Exempt liquidation from the circuit break check, or create a separate "soft circuit break" that only blocks deposits and borrows while still allowing withdrawals, repayments, and liquidations:

```move
fun pre_liquidation_check<MarketType>(
    app: &ProtocolApp,
    cap: &PackageCallerCap,
    market: &Market<MarketType>,
    permission: u8,
) {
    app.validate_market<MarketType>(market);
    app.ensure_version_matches();
    app.ensure_has_permission(object::id(cap), permission);
    // Remove circuit break check for liquidation
    // Liquidation should always be allowed to prevent bad debt
}
```

Alternatively, implement a two-tier circuit break:
- **Level 1 (Soft)**: Block new deposits and borrows only
- **Level 2 (Hard)**: Block all operations (current behavior, reserved for contract migration)

Manual Review + Automated Analysis
