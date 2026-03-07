# Circuit Break Blocks Liquidation, Allowing Bad Debt Accumulation

## Summary

When the market's circuit breaker is triggered, all operations including liquidation are blocked. This prevents liquidators from closing underwater positions, allowing bad debt to accumulate unchecked during the circuit break period.

## Vulnerability Detail

In `liquidate.move:48-60`, the `pre_liquidation_check` function is called before every liquidation type (normal, ADL borrow, ADL collateral):

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

This means all three liquidation paths are gated by circuit break:
- `liquidate` / `liquidate_as_coin` (line 177 via `pre_liquidation_check`)
- `liquidate_adl_borrow` (line 224)
- `liquidate_adl_deposit` (line 273)

The circuit breaker at `market.move:119-124` is a simple boolean that blocks all operations:

```move
public(package) fun trigger_circuit_break<MarketType>(self: &mut Market<MarketType>) {
    let is_circuit_break = dynamic_field::borrow_mut(&mut self.id, CircuitBreakKey {});
    assert!(!*is_circuit_break, error::already_under_circuit_break());
    *is_circuit_break = true;
}
```

**Attack scenario:**
1. Market experiences a price shock or oracle failure, prompting admin to trigger circuit break
2. During the circuit break, collateral prices may continue dropping
3. Obligations that were marginally underwater become deeply underwater
4. No liquidation can occur to stem the bleeding
5. When circuit break is lifted, a cascade of bad debt positions exists that may exceed protocol reserves
6. If the bad debt exceeds the 101% threshold (line 985-992 of market.move), all close factor limits are bypassed, leading to a liquidation rush

This is the opposite of the desired behavior: circuit break should be a protective measure, but blocking liquidation actually amplifies systemic risk.

## Impact

- **Bad debt accumulation during emergencies**: The exact scenario where liquidation is most needed (market stress) is when it's blocked
- **Cascading insolvency**: Positions that could have been safely liquidated during circuit break may become irreversibly insolvent
- **Protocol loss socialization**: Bad debt must be absorbed by the protocol or socialized across depositors

Severity is Medium because it requires admin action (triggering circuit break) and a concurrent market downturn, but the impact is systemic and can threaten protocol solvency.

## Code Snippet

- [`liquidate.move:59`](contracts/protocol/sources/entry_points/lending/liquidate.move#L59): `assert!(!market.has_circuit_break_triggered())`
- [`liquidate.move:177`](contracts/protocol/sources/entry_points/lending/liquidate.move#L177): Normal liquidation calls `pre_liquidation_check`
- [`liquidate.move:224`](contracts/protocol/sources/entry_points/lending/liquidate.move#L224): ADL borrow calls `pre_liquidation_check`
- [`liquidate.move:273`](contracts/protocol/sources/entry_points/lending/liquidate.move#L273): ADL collateral calls `pre_liquidation_check`

## Tool used

Manual Review + Automated Analysis

## Recommendation

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
