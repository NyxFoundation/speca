# `create_market_asset_config` Missing `max >= min` and `max > 0` Validation

## Summary

`create_market_asset_config` validates `min_borrow_amount > 0` and fee rates, but does not validate that `max_borrow_amount >= min_borrow_amount` or `max_deposit_amount > 0`. An admin can create a config where `max_borrow_amount < min_borrow_amount` or `max_deposit_amount = 0`, bricking the asset's borrow or deposit functionality.

## Vulnerability Detail

At `asset.move:69-95`:

```move
public fun create_market_asset_config(
    _: &AdminCap,
    self: &ProtocolApp,
    min_borrow_amount: u64,
    max_borrow_amount: u64,
    max_deposit_amount: u64,
    repay_fee_rate: u64,
    liquidation_fee_rate: u64,
): AssetConfig {
    // Validate parameters
    assert!(min_borrow_amount > 0, error::invalid_params_error());
    assert!(liquidation_fee_rate <= DECIMAL_DENOMINATOR, error::invalid_params_error());
    assert!(repay_fee_rate <= DECIMAL_DENOMINATOR, error::invalid_params_error());

    self.ensure_version_matches();

    let liquidation_fee = math::float::from_quotient(liquidation_fee_rate, DECIMAL_DENOMINATOR);
    let repay_fee = math::float::from_quotient(repay_fee_rate, DECIMAL_DENOMINATOR);

    protocol::asset::new_asset_config(
        min_borrow_amount,
        max_borrow_amount,
        repay_fee,
        max_deposit_amount,
        liquidation_fee
    )
}
```

Missing validations:
1. `max_borrow_amount >= min_borrow_amount` — if `max_borrow_amount < min_borrow_amount`, no borrow amount can satisfy both constraints simultaneously, making borrowing impossible for this asset.
2. `max_deposit_amount > 0` — if `max_deposit_amount = 0`, the deposit limit check will reject all deposits.
3. `max_borrow_amount > 0` — if `max_borrow_amount = 0`, no borrows are possible.

The `update_market_asset_config` function (line 98-118) also lacks these validations, as it accepts an already-constructed `AssetConfig` and applies it directly.

## Internal Pre-conditions

1. Admin must call `create_market_asset_config` with misconfigured values.

## External Pre-conditions

None.

## Attack Path

1. Admin creates asset config with `min_borrow_amount = 1000`, `max_borrow_amount = 500` (misconfiguration, perhaps confusing parameter order).
2. Config is applied via `onboard_new_asset` or `update_market_asset_config`.
3. All borrow attempts for this asset fail: amounts ≥ 1000 exceed `max_borrow_amount`, amounts ≤ 500 are below `min_borrow_amount`.
4. The asset is effectively bricked for borrowing until admin detects and corrects the config.

## Impact

Admin misconfiguration can brick an asset's borrow or deposit functionality. This is a defensive programming issue — the function should reject obviously invalid configurations at creation time rather than allowing them to propagate. The impact is limited by the admin-gated nature of the function, but the lack of validation creates an operational risk. Recovery requires a separate admin transaction to update the config.

## Code Snippet

- `contracts/protocol/sources/entry_points/admin/asset.move:69-95` — `create_market_asset_config` missing `max >= min` validation
- `contracts/protocol/sources/entry_points/admin/asset.move:98-118` — `update_market_asset_config` passes through without validation

## Tool used

Manual Review

## Mitigation

Add validation for parameter consistency:

```move
public fun create_market_asset_config(
    _: &AdminCap,
    self: &ProtocolApp,
    min_borrow_amount: u64,
    max_borrow_amount: u64,
    max_deposit_amount: u64,
    repay_fee_rate: u64,
    liquidation_fee_rate: u64,
): AssetConfig {
    assert!(min_borrow_amount > 0, error::invalid_params_error());
    assert!(max_borrow_amount >= min_borrow_amount, error::invalid_params_error());
    assert!(max_deposit_amount > 0, error::invalid_params_error());
    assert!(liquidation_fee_rate <= DECIMAL_DENOMINATOR, error::invalid_params_error());
    assert!(repay_fee_rate <= DECIMAL_DENOMINATOR, error::invalid_params_error());
    // ...
}
```
