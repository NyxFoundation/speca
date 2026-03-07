# Admin Removing Asset from eMode Group Permanently Freezes Affected Obligations

## Summary

If an admin removes an asset from an eMode group while obligations in that group hold deposits of that asset, those obligations become permanently frozen — all operations (withdraw, borrow, liquidation, ADL) revert because `borrow_emode()` aborts on unsupported asset types.

## Vulnerability Detail

The function `refresh_obligation_assets_interest` (market.move:858-886) iterates over all deposit types in an obligation and calls `emode_group.borrow_emode(name)` for each:

```move
// market.move:876
let collateral_settings = emode_group.borrow_emode(name).collateral();
```

The `borrow_emode` function (emode.move:375-378) contains a hard assertion:

```move
// emode.move:375-378
public(package) fun borrow_emode(self: &EModeGroup, asset: TypeName): &EMode {
    assert!(self.assets.supports_type(asset), error::emode_group_does_not_support_asset());
    self.assets.load_by_type(asset)
}
```

If an asset has been removed from the eMode group, this assertion aborts the entire transaction. Since `refresh_obligation_assets_interest` is called by:
- `handle_withdraw` (market.move:326) — via `refresh_obligation_assets_interest`
- `liquidation_inner` (market.move:720) — prevents liquidation
- `handle_debt_auto_deleverage` — prevents ADL
- `handle_collateral_auto_deleverage` — prevents ADL

The obligation becomes completely frozen: the owner cannot withdraw their collateral, and the position cannot be liquidated even if it becomes underwater. Note that on line 882, there is a `can_be_collateral()` check that would gracefully skip non-collateral assets, but it is never reached because the `borrow_emode` assertion on line 876 reverts first.

Similarly, `collaterals_usd_for_liquidation` (market.move:1105) and `collaterals_usd_non_liquidation` (market.move:1277) also call `borrow_emode(deposit_type)` without first checking whether the asset is still in the group.

## Impact

An admin governance action (removing an asset from an eMode group) can permanently freeze all obligations that hold deposits of that asset. The frozen obligations:
- Cannot be withdrawn from (user funds locked)
- Cannot be liquidated (bad debt accumulates)
- Cannot be ADL'd (emergency mechanism fails)

This creates a permanent denial-of-service for affected users and prevents the protocol from managing risk on underwater positions.

## Code Snippet

- emode.move:375-378 (hard assertion in `borrow_emode`)
- market.move:876 (called in `refresh_obligation_assets_interest`)
- market.move:1105 (called in `collaterals_usd_for_liquidation`)
- market.move:1277 (called in `collaterals_usd_non_liquidation`)

## Tool used

Manual Review + Automated Analysis

## Recommendation

Add a graceful fallback in `refresh_obligation_assets_interest` that skips assets no longer in the eMode group, or add a `try_borrow_emode` function that returns `Option` instead of aborting:

```move
// Option 1: Check before calling borrow_emode
while (i < n) {
    let name = asset_types[i];
    i = i + 1;

    // Skip assets no longer in eMode group
    if (!emode_group.supports_asset(name)) { continue };

    let collateral_settings = emode_group.borrow_emode(name).collateral();
    if (!collateral_settings.can_be_collateral()) { continue };

    accrue_interest<MarketType>(name, reserves, asset.asset_config(), asset.interest_model(), now);
};
```

Also apply the same pattern to `collaterals_usd_for_liquidation` and `collaterals_usd_non_liquidation`.
