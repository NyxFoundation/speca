# ADL Paths Bypass `liquidation_paused` Safety Check

## Summary

Both `handle_debt_auto_deleverage` and `handle_collateral_auto_deleverage` lack the `liquidation_paused` assertion that exists in normal liquidation (`handle_liquidation`), allowing ADL liquidations to proceed on paused assets.

## Vulnerability Detail

In `handle_liquidation` (market.move:520), the protocol checks whether liquidation is paused for the collateral asset:

```move
// market.move:519-520
let asset = self.assets.load_mut_by_type(collateral_name);
assert!(!asset.liquidation_paused(), error::liquidation_paused_for_asset());
```

However, neither `handle_debt_auto_deleverage` (market.move:546-611) nor `handle_collateral_auto_deleverage` (market.move:613-677) perform this check. In `handle_debt_auto_deleverage`, the only validations are:

```move
// market.move:567-569
let collateral_setting = emode_group.borrow_emode(collateral_type).collateral();
assert!(collateral_setting.can_be_collateral(), error::asset_not_collateral());
```

The `liquidation_paused` flag is never checked for either the collateral or debt asset. Similarly, `handle_collateral_auto_deleverage` (market.move:638-641) only checks `can_be_collateral()`.

The admin's ability to pause liquidation exists as an emergency safety mechanism — for example, when an oracle is suspected of manipulation or a price feed becomes unreliable. If ADL ignores this flag, admin cannot effectively prevent forced liquidations during emergencies.

## Impact

When an admin pauses liquidation on a specific asset (e.g., due to suspected oracle manipulation or a depegging event), ADL liquidations can still seize collateral or repay debt involving that asset. This defeats the emergency pause mechanism and allows potentially harmful liquidations based on unreliable price data to proceed.

## Code Snippet

- market.move:520 (normal liquidation paused check)
- market.move:546-611 (handle_debt_auto_deleverage — no paused check)
- market.move:613-677 (handle_collateral_auto_deleverage — no paused check)

## Tool used

Manual Review + Automated Analysis

## Recommendation

Add `liquidation_paused` checks to both ADL functions:

```move
// In handle_debt_auto_deleverage, after line 569:
let collateral_asset = self.assets.load_by_type(collateral_type);
assert!(!collateral_asset.liquidation_paused(), error::liquidation_paused_for_asset());

// In handle_collateral_auto_deleverage, after line 641:
let collateral_asset = self.assets.load_by_type(collateral);
assert!(!collateral_asset.liquidation_paused(), error::liquidation_paused_for_asset());
```
