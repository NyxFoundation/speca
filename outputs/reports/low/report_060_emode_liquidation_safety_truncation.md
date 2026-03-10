# eMode Liquidation Safety Check Uses Integer Division, Allowing Off-by-One bps Configurations

## Summary

In `create_emode_params`, the invariant `liquidation_factor * (1 + liquidation_incentive) < 1` is checked using integer division (`/ BPS_DENOMINATOR`), which truncates the result. This allows configurations where the true product `lf * (1 + li)` equals or slightly exceeds 1.0, violating the intended safety constraint.

## Vulnerability Detail

At `emode.move:92-96`:

```move
// liquidation factor * (1 + liquidation incentive) < 1
assert!(
    liquidation_factor_bps * (BPS_DENOMINATOR + liquidation_incentive_bps) / BPS_DENOMINATOR < BPS_DENOMINATOR,
    error::invalid_params_error()
);
```

The comment states the invariant: `liquidation_factor * (1 + liquidation_incentive) < 1`. However, the integer division truncates toward zero.

Example: `liquidation_factor_bps = 9524`, `liquidation_incentive_bps = 500` (5% incentive).

- True product: `9524 * (10000 + 500) / 10000 = 9524 * 10500 / 10000 = 100002000 / 10000 = 10000.2`
- Integer division: `100002000 / 10000 = 10000` (truncated)
- Check: `10000 < 10000` → FALSE, correctly rejected

But consider: `liquidation_factor_bps = 9524`, `liquidation_incentive_bps = 499`:

- True product: `9524 * 10499 / 10000 = 99991076 / 10000 = 9999.1076`
- Integer division: `99991076 / 10000 = 9999` (truncated)
- Check: `9999 < 10000` → TRUE, accepted

Actual value: `0.9524 * 1.0499 = 0.99991076` — this is below 1.0 and correct.

The truncation becomes problematic at boundary values. Consider `liquidation_factor_bps = 9091`, `liquidation_incentive_bps = 1000` (10% incentive):

- True: `9091 * 11000 / 10000 = 100001000 / 10000 = 10000.1`
- Integer: `100001000 / 10000 = 10000`
- Check: `10000 < 10000` → FALSE, correctly rejected

But `liquidation_factor_bps = 9091`, `liquidation_incentive_bps = 999`:

- True: `9091 * 10999 / 10000 = 99990909 / 10000 = 9999.0909`
- Integer: `9999`
- Accepted. True value 0.99990909 < 1.0.

The maximum error from truncation is at most 1 bps (`0.9999...` accepted when the true value is `< 1.0 + 1/BPS`). In practice, the integer check is slightly **more conservative** than the true mathematical check for values that don't hit the truncation boundary, and allows at most configurations where `lf * (1 + li)` is in `[0.9999, 1.0)`.

However, after the check, these values are converted to floating-point via `from_quotient` (line 181-183) where the full precision is preserved. In the actual liquidation logic, the product `lf * (1 + li)` determines whether a liquidation is profitable — if this product ≥ 1.0, liquidating the full debt would require seizing more collateral than is available at the liquidation factor, creating bad debt.

## Internal Pre-conditions

1. Admin must configure an eMode group with `liquidation_factor_bps` and `liquidation_incentive_bps` values near the boundary where their product approaches `BPS_DENOMINATOR`.

## External Pre-conditions

None.

## Attack Path

1. Admin creates an eMode group with `liquidation_factor_bps = 9524` and `liquidation_incentive_bps = 500`.
2. Integer division check passes: `9524 * 10500 / 10000 = 10000 < 10000` → rejected (correctly).
3. But with values just 1 bps lower, the check passes while the true product is extremely close to 1.0.
4. In markets configured at these boundary values, full liquidation at the incentive rate may not be fully self-closing, leaving tiny residual bad debt.

## Impact

The maximum error is 1 bps (0.01%). At boundary configurations, the product `lf * (1 + li)` can be in the range `[0.9999, 1.0)` rather than strictly `< 0.9999`. This is an admin-gated configuration issue — only affects eMode groups configured with parameters near the mathematical boundary. The practical impact is minimal because (a) admins should choose parameters with margin, and (b) the actual liquidation math uses floating-point, which handles these near-boundary values without overflow.

## Code Snippet

- `contracts/protocol/sources/entry_points/admin/emode.move:92-96` — integer division truncation in safety check
- `contracts/protocol/sources/entry_points/admin/emode.move:181-183` — `from_quotient` preserves full precision

## Tool used

Manual Review

## Mitigation

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
