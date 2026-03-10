### eMode Liquidation Safety Check Uses Integer Division, Allowing Off-by-One bps Configurations

Admin will allow near-boundary eMode configurations that may leave residual bad debt for the protocol

### Summary

The integer division truncation in `create_emode_params` (using `/ BPS_DENOMINATOR` instead of multiply-then-compare) will cause acceptance of configurations where `liquidation_factor * (1 + liquidation_incentive)` is in the range `[0.9999, 1.0)` for the protocol as the admin creating an eMode group with boundary parameters will pass the truncated check while the true product approaches 1.0, potentially leaving tiny residual bad debt during full liquidations.

### Root Cause

In [`contracts/protocol/sources/entry_points/admin/emode.move:92-96`](contracts/protocol/sources/entry_points/admin/emode.move#L92-L96) the safety invariant `liquidation_factor * (1 + liquidation_incentive) < 1` is checked using integer division which truncates toward zero:

```move
// liquidation factor * (1 + liquidation incentive) < 1
assert!(
    liquidation_factor_bps * (BPS_DENOMINATOR + liquidation_incentive_bps) / BPS_DENOMINATOR < BPS_DENOMINATOR,
    error::invalid_params_error()
);
```

The truncation allows configurations where the true product is in `[0.9999, 1.0)`. After the check, at [`emode.move:181-183`](contracts/protocol/sources/entry_points/admin/emode.move#L181-L183), values are converted via `from_quotient` preserving full precision, so the actual liquidation logic operates with the near-1.0 product.

Example: `liquidation_factor_bps = 9524`, `liquidation_incentive_bps = 499`:
- True product: `9524 * 10499 / 10000 = 0.99991076`
- Integer division: `99991076 / 10000 = 9999` (truncated)
- Check: `9999 < 10000` passes, but the product is extremely close to 1.0

### Internal Pre-conditions

1. [Admin needs to configure an eMode group to set] `liquidation_factor_bps` and `liquidation_incentive_bps` to values near the boundary where their product approaches `BPS_DENOMINATOR`.

### External Pre-conditions

None.

### Attack Path

1. Admin creates an eMode group with `liquidation_factor_bps` and `liquidation_incentive_bps` near the mathematical boundary.
2. Integer division truncation causes the safety check to pass despite the true product being in `[0.9999, 1.0)`.
3. The values are stored and converted to floating-point via `from_quotient` with full precision.
4. In markets configured at these boundary values, full liquidation at the incentive rate may not be fully self-closing, leaving tiny residual bad debt.

### Impact

The protocol suffers potential residual bad debt from eMode groups configured at boundary parameters where `lf * (1 + li)` is in `[0.9999, 1.0)`. The maximum error is 1 bps (0.01%). This is limited by the admin-gated nature of the function and the expectation that admins choose parameters with margin.

### PoC

_No PoC provided._

### Mitigation

Use ceiling division or multiply-then-compare to avoid truncation:

```move
// Option 1: multiply-then-compare (no division)
assert!(
    liquidation_factor_bps * (BPS_DENOMINATOR + liquidation_incentive_bps) < BPS_DENOMINATOR * BPS_DENOMINATOR,
    error::invalid_params_error()
);

// Option 2: add (BPS_DENOMINATOR - 1) before dividing for ceiling division
assert!(
    (liquidation_factor_bps * (BPS_DENOMINATOR + liquidation_incentive_bps) + BPS_DENOMINATOR - 1) / BPS_DENOMINATOR < BPS_DENOMINATOR,
    error::invalid_params_error()
);
```
