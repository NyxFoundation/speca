# Normal Liquidation Only Checks Collateral Asset Pause State, Not Debt Asset

## Summary

In `handle_liquidation`, only the collateral asset's `liquidation_paused` flag is checked. The debt asset's pause state is never verified, allowing liquidations to proceed even when the admin has paused liquidation for the debt asset.

## Root Cause

In [`market.move:519-520`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L519-L520), `handle_liquidation` only checks the collateral asset's `liquidation_paused` flag but never checks the debt asset's pause state. The `liquidation_paused` getter exists in [`asset.move:48`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/asset.move#L48) but is not called for the debt asset.

```move
public(package) fun handle_liquidation<MarketType, DebtType, CollateralType>(
    self: &mut Market<MarketType>,
    ...
) {
    // ...
    let collateral_name = type_name::with_defining_ids<CollateralType>();
    // ...
    let asset = self.assets.load_mut_by_type(collateral_name);
    assert!(!asset.liquidation_paused(), error::liquidation_paused_for_asset());  // Only checks collateral
    // ...
}
```

There is no corresponding check for the debt asset:
```move
let debt_asset = self.assets.load_by_type(type_name::with_defining_ids<DebtType>());
assert!(!debt_asset.liquidation_paused(), error::liquidation_paused_for_asset());  // MISSING
```

This means if the admin pauses liquidation for asset X (intending to prevent any liquidation involving asset X), liquidations where X is the **debt** being repaid will still proceed. Only liquidations where X is the **collateral** being seized are blocked.

Note: The ADL liquidation paths (`handle_debt_auto_deleverage` and `handle_collateral_auto_deleverage`) also do not check either asset's `liquidation_paused` state, but this may be intentional since ADL is a separate emergency mechanism.

## Internal Pre-conditions

1. The protocol must have an asset with an active `liquidation_paused` flag set to `true` by the admin via `change_operation_status`.
2. There must be existing borrowing obligations where the paused asset is used as the debt asset.

## External Pre-conditions

1. An oracle issue or price feed compromise must affect the paused asset, motivating the admin to pause liquidation for that asset.
2. Liquidators must be monitoring for liquidation opportunities involving the paused asset as a debt asset.

## Attack Path

1. Admin discovers an oracle issue affecting Token A's price feed.
2. Admin pauses liquidation for Token A via `change_operation_status` to prevent incorrect liquidations.
3. Liquidators can still liquidate obligations where Token A is the debt asset (repaying Token A to seize other collateral), because only the collateral asset's pause state is checked.
4. If the oracle is reporting an inflated price for Token A, this allows liquidators to over-repay (at the inflated debt valuation) and over-seize collateral.

## Impact

- **Incomplete pause mechanism**: Admin cannot fully pause liquidation for an asset experiencing oracle issues.
- **Incorrect liquidations during oracle incidents**: When an asset's price feed is compromised, pausing only blocks half the liquidation paths.
- **Loss of funds**: Borrowers may be unfairly liquidated using a debt asset whose liquidation was intended to be paused.

Severity is Medium because it requires admin action (pausing) in response to an incident, but undermines the protocol's emergency controls at a critical time.

## PoC

Code inspection of `handle_liquidation` in `market.move:496-528` confirms that only the collateral asset's `liquidation_paused` flag is checked:

```move
let collateral_name = type_name::with_defining_ids<CollateralType>();
// ...
let asset = self.assets.load_mut_by_type(collateral_name);
assert!(!asset.liquidation_paused(), error::liquidation_paused_for_asset());
```

No equivalent check exists for `DebtType`. The `liquidation_paused()` getter is defined in `asset.move:48` and is available for use, but `handle_liquidation` never loads the debt asset to verify its pause state. This can be confirmed by searching the function body for any reference to `DebtType` in conjunction with `liquidation_paused` — no such reference exists.

## Mitigation

Add a debt asset pause check in `handle_liquidation`:

```move
public(package) fun handle_liquidation<MarketType, DebtType, CollateralType>(...) {
    // ... existing collateral checks ...
    let asset = self.assets.load_mut_by_type(collateral_name);
    assert!(!asset.liquidation_paused(), error::liquidation_paused_for_asset());

    // Add debt asset pause check
    let debt_asset = self.assets.load_by_type(type_name::with_defining_ids<DebtType>());
    assert!(!debt_asset.liquidation_paused(), error::liquidation_paused_for_asset());
    // ...
}
```

## Tool used

Manual Review + Automated Analysis
