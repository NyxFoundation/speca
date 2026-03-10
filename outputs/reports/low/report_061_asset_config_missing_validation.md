### `create_market_asset_config` Missing `max >= min` and `max > 0` Validation

Admin will brick an asset's borrow or deposit functionality for all users of that asset

### Summary

The missing validation in `create_market_asset_config` (no checks for `max_borrow_amount >= min_borrow_amount` or `max_deposit_amount > 0`) will cause bricked borrow or deposit functionality for all users of the affected asset as the admin passing misconfigured values will create an asset config where no valid borrow amount can satisfy both constraints simultaneously.

### Root Cause

In [`contracts/protocol/sources/entry_points/admin/asset.move:69-95`](contracts/protocol/sources/entry_points/admin/asset.move#L69-L95) the `create_market_asset_config` function validates `min_borrow_amount > 0` and fee rates but omits critical consistency checks:

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
    // Only these are validated:
    assert!(min_borrow_amount > 0, error::invalid_params_error());
    assert!(liquidation_fee_rate <= DECIMAL_DENOMINATOR, error::invalid_params_error());
    assert!(repay_fee_rate <= DECIMAL_DENOMINATOR, error::invalid_params_error());
    // Missing: max_borrow_amount >= min_borrow_amount
    // Missing: max_deposit_amount > 0
    // Missing: max_borrow_amount > 0
    // ...
}
```

The [`update_market_asset_config`](contracts/protocol/sources/entry_points/admin/asset.move#L98-L118) function at line 98-118 also lacks these validations, as it accepts an already-constructed `AssetConfig` and applies it directly.

### Internal Pre-conditions

1. [Admin needs to call `create_market_asset_config` to set] `max_borrow_amount` to be less than `min_borrow_amount` (e.g., confusing parameter order).

### External Pre-conditions

None.

### Attack Path

1. Admin creates asset config with `min_borrow_amount = 1000`, `max_borrow_amount = 500` (misconfiguration, perhaps confusing parameter order).
2. Config is applied via `onboard_new_asset` or `update_market_asset_config`.
3. All borrow attempts for this asset fail: amounts >= 1000 exceed `max_borrow_amount`, amounts <= 500 are below `min_borrow_amount`.
4. The asset is effectively bricked for borrowing until admin detects and corrects the config.

### Impact

The users of the affected asset suffer a complete denial-of-service on borrow or deposit functionality until the admin corrects the misconfiguration via a separate admin transaction.

### PoC

_No PoC provided._

### Mitigation

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
