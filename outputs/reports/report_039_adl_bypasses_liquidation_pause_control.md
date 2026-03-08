# ADL Liquidation Bypasses Asset Liquidation Pause Controls

## Summary
The protocol enforces `liquidation_paused` only in the normal liquidation path. Both ADL liquidation entrypoints execute liquidation logic without checking the pause flag, allowing liquidations while admins believe liquidation is paused.

## Vulnerability Detail
In normal liquidation, `handle_liquidation` explicitly checks collateral pause state:

- loads collateral asset
- `assert!(!asset.liquidation_paused(), ...)`

However, ADL liquidation paths do not perform this check:

- `handle_debt_auto_deleverage`
- `handle_collateral_auto_deleverage`

Both functions proceed into `liquidation_inner` directly, so once ADL is active, an allowed caller can still seize collateral even for assets intentionally paused for liquidation (e.g., oracle incident, market stress, migration window).

This creates a control-plane bypass: admin pause signals are not consistently enforced across liquidation modes.

## Internal Pre-conditions

1. Admin must have paused liquidation for a specific asset.
2. ADL must be active for the relevant eMode group.

## External Pre-conditions

None.

## Attack Path

1. Admin pauses liquidation for asset X due to oracle incident.
2. ADL is active for the eMode group containing asset X.
3. ADL liquidator calls liquidate_adl_borrow or liquidate_adl_deposit.
4. handle_debt_auto_deleverage / handle_collateral_auto_deleverage proceed without checking liquidation_paused.
5. Collateral of paused asset X is seized despite admin's pause order.

## Impact
- Emergency liquidation pause is ineffective for ADL routes
- Operators may assume liquidation is halted while ADL liquidations continue
- During incident response, users can still be liquidated via ADL, increasing loss and operational risk
- Policy mismatch undermines risk controls

## Code Snippet
- `contracts/protocol/sources/internal/market/market.move:519-521` (normal liquidation pause check)
- `contracts/protocol/sources/internal/market/market.move:546-611` (ADL borrow path without pause check)
- `contracts/protocol/sources/internal/market/market.move:613-677` (ADL collateral path without pause check)
- `contracts/protocol/sources/entry_points/lending/liquidate.move:210-305` (ADL entrypoints that reach these paths)

## Tool used
Manual Review + Automated Analysis

## Mitigation
Enforce the same `liquidation_paused` guard in ADL paths before invoking `liquidation_inner`.

Example hardening:

```move
let collateral_name = type_name::with_defining_ids<CollateralType>();
let collateral_asset = self.assets.load_by_type(collateral_name);
assert!(!collateral_asset.liquidation_paused(), error::liquidation_paused_for_asset());
```

Apply this consistently in both `handle_debt_auto_deleverage` and `handle_collateral_auto_deleverage`.
