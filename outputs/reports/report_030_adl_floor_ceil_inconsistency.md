# ADL Collateral Deleverage Uses Inconsistent Rounding Between Trigger and Stop Checks

## Summary

`handle_collateral_auto_deleverage` uses `floor()` to compute `total_deposit` for the trigger check (`ensure_limit_breached`), but `try_stop_collateral_deleverage` uses `ceil()` for the stop check. This rounding inconsistency can create an edge case where ADL is perpetually triggered but can never be stopped.

## Vulnerability Detail

In `market.move:649`, the ADL trigger check computes total deposit with `floor()`:

```move
public(package) fun handle_collateral_auto_deleverage<MarketType, DebtType, CollateralType>(
    self: &mut Market<MarketType>,
    ...
) {
    // ...
    let total_deposit = self.reserves.load_by_type(collateral).cash_plus_borrows_minus_reserves().floor();
    let collateral_params = timelock.inner();
    collateral_params.ensure_limit_breached(total_deposit);  // uses floor()
    // ...
}
```

But in `market.move:679-683`, the stop check uses `ceil()`:

```move
fun try_stop_collateral_deleverage<MarketType, CollateralType>(
    id: &mut UID,
    reserves: &GenericCoinTypeStorage<Reserve<MarketType>>,
    collateral: TypeName,
) {
    let total_deposit = reserves.load_by_type(collateral).cash_plus_borrows_minus_reserves().ceil();
    let adl = dynamic_field::borrow_mut<ADLRegistryKey, AutoDeleverageRegistry>(id, ADLRegistryKey {});
    adl.try_stop_collateral_deleverage<CollateralType>(..., total_deposit);
}
```

The `ensure_limit_breached` check requires `target_amount < current_value` (total deposit below the limit). The `try_stop_collateral_deleverage` check presumably stops ADL when total deposit recovers above the limit.

When `cash_plus_borrows_minus_reserves()` returns a fractional value V where `floor(V) < limit <= ceil(V)`:
- The trigger check sees `floor(V) < limit` → ADL remains active
- The stop check sees `ceil(V) >= limit` → ADL stop also fires
- After each ADL liquidation reduces deposits slightly, we return to the same state

This creates an oscillation zone where ADL is always considered "breached" (using floor) but also always tries to stop (using ceil), leading to unpredictable behavior at the boundary.

Note: The borrow ADL path has an inverse but similar inconsistency — `handle_debt_auto_deleverage` uses `floor()` (market.move:580) while `handle_repay` uses `ceil()` for `try_stop_borrow_deleverage` (market.move:491), though the comparison directions differ.

## Impact

- **ADL oscillation at boundary**: Near the ADL threshold, collateral deleveraging may exhibit inconsistent trigger/stop behavior
- **Unnecessary ADL liquidations**: Positions may be ADL-liquidated even when the true total deposit is at or above the threshold
- **User fund loss**: ADL liquidation typically has less favorable terms for the liquidated user

Severity is Low because the edge case requires the total deposit to land exactly in the narrow band between floor and ceil of the threshold value, but the impact when triggered affects user funds through unnecessary forced liquidation.

## Code Snippet

- [`market.move:649`](contracts/protocol/sources/internal/market/market.move#L649): `cash_plus_borrows_minus_reserves().floor()` for trigger check
- [`market.move:680`](contracts/protocol/sources/internal/market/market.move#L680): `cash_plus_borrows_minus_reserves().ceil()` for stop check
- [`market.move:580`](contracts/protocol/sources/internal/market/market.move#L580): Borrow ADL trigger also uses `floor()`
- [`market.move:491`](contracts/protocol/sources/internal/market/market.move#L491): Repay ADL stop uses `ceil()`

## Tool used

Manual Review + Automated Analysis

## Recommendation

Use consistent rounding for both trigger and stop checks. Using `ceil()` for both is the conservative choice (ADL triggers less easily, stops more easily):

```move
// In handle_collateral_auto_deleverage:
let total_deposit = self.reserves.load_by_type(collateral).cash_plus_borrows_minus_reserves().ceil();

// In try_stop_collateral_deleverage (already uses ceil):
let total_deposit = reserves.load_by_type(collateral).cash_plus_borrows_minus_reserves().ceil();
```

Or use `floor()` for both if the protocol prefers a more aggressive ADL trigger.
