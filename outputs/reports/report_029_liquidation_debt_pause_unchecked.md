# Normal Liquidation Only Checks Collateral Asset Pause State, Not Debt Asset

## Summary

In `handle_liquidation`, only the collateral asset's `liquidation_paused` flag is checked. The debt asset's pause state is never verified, allowing liquidations to proceed even when the admin has paused liquidation for the debt asset.

## Vulnerability Detail

In `market.move:496-528`, `handle_liquidation` loads the collateral asset and checks its pause state:

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

**Scenario:**
1. Admin discovers an oracle issue affecting Token A's price feed
2. Admin pauses liquidation for Token A via `change_operation_status` to prevent incorrect liquidations
3. Liquidators can still liquidate obligations where Token A is the debt asset (repaying Token A to seize other collateral), because only collateral asset pause is checked
4. If the oracle is reporting an inflated price for Token A, this allows liquidators to over-repay (at the inflated debt valuation) and over-seize collateral

Note: The ADL liquidation paths (`handle_debt_auto_deleverage` and `handle_collateral_auto_deleverage`) also do not check either asset's `liquidation_paused` state, but this may be intentional since ADL is a separate emergency mechanism.

## Impact

- **Incomplete pause mechanism**: Admin cannot fully pause liquidation for an asset experiencing oracle issues
- **Incorrect liquidations during oracle incidents**: When an asset's price feed is compromised, pausing only blocks half the liquidation paths
- **Loss of funds**: Borrowers may be unfairly liquidated using a debt asset whose liquidation was intended to be paused

Severity is Medium because it requires admin action (pausing) in response to an incident, but undermines the protocol's emergency controls at a critical time.

## Code Snippet

- [`market.move:519-520`](contracts/protocol/sources/internal/market/market.move#L519-L520): Only collateral asset's `liquidation_paused` is checked
- [`asset.move:48`](contracts/protocol/sources/internal/market/asset.move#L48): `liquidation_paused` getter exists but is not called for debt asset

## Tool used

Manual Review + Automated Analysis

## Recommendation

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
