### Zero flash_loan_fee_rate configuration permanently bricks flash loans for affected eMode group

### Summary

Missing validation that `flash_loan_fee_rate_bps > 0` in `create_emode_params_inner` will cause all flash loans for the affected eMode group to revert as `borrow_flash_loan` asserts `fee != 0`.

### Root Cause

In [`emode_admin.move:179`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/admin/emode.move#L179), the validation only checks `flash_loan_fee_rate_bps < BPS_DENOMINATOR` but does NOT check `> 0`:

```move
assert!(flash_loan_fee_rate_bps < BPS_DENOMINATOR, error::invalid_params_error());
```

When `flash_loan_fee_rate_bps = 0`, the fee becomes 0 in [`market.move:813`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L813-L814):

```move
let fee = flash_loan_fee_rate.int_mul(amount);
assert!(fee != 0, error::reserve_flash_loan_fee_too_small());
```

The assert always fails, permanently blocking flash loans until admin updates the fee rate.

### Internal Pre-conditions

1. Admin needs to set `flash_loan_fee_rate_bps` to `0` for an eMode group asset.

### External Pre-conditions

None.

### Attack Path

1. Admin onboards an asset to an eMode group with `flash_loan_fee_rate_bps = 0` (accidentally or intentionally thinking "no fee" is valid).
2. Any whitelisted flash loan borrower tries to borrow this asset.
3. `borrow_flash_loan` calculates fee = 0, asserts `fee != 0` → transaction reverts.
4. Flash loans are permanently blocked for this asset in this eMode group until admin corrects the fee.

### Impact

All flash loan operations for the affected eMode group asset are blocked (DoS). Protocols integrating with Current Finance's flash loan functionality would be disrupted. Admin can fix by calling `update_asset_in_emode_group` with a non-zero fee rate.

### PoC

```
// In create_emode_params_inner (emode_admin.move:179):
// flash_loan_fee_rate_bps = 0 passes validation:
//   assert!(0 < 10000, ...) → PASSES
//
// In borrow_flash_loan (market.move:813):
//   fee = 0.int_mul(any_amount) = 0
//   assert!(0 != 0, ...) → REVERTS
```

### Mitigation

Add `> 0` check in `create_emode_params_inner`:

```move
assert!(flash_loan_fee_rate_bps > 0 && flash_loan_fee_rate_bps < BPS_DENOMINATOR, error::invalid_params_error());
```
