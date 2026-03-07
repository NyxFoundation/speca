# Liquidation Protocol-Fee Bypass via Chunked Small Liquidations

## Summary

Liquidators can split a single liquidation into many tiny chunks, causing the protocol's liquidation revenue fee to round down to zero on each chunk. This allows liquidators to capture 100% of the liquidation bonus while the protocol receives no revenue.

## Vulnerability Detail

The protocol charges a `liquidation_revenue_factor` fee on every liquidation, intended to route a portion of seized collateral to the protocol's reserves. This fee is computed via `int_mul()` which performs **truncating integer division** (floors to zero for small amounts):

```move
// reserve.move:175-176
let protocol_seize_amount = liq_revenue_factor.int_mul(redeem_collateral_amount);
let liquidator_seize_amount = redeem_collateral_amount - protocol_seize_amount;
```

The `int_mul` function in `float.move:63-65`:
```move
public fun int_mul(a: Decimal, b: u64): u64 {
    safe_from_u256((a.value * (b as u256)) / WAD)
}
```

This uses integer division which **floors** the result. When `redeem_collateral_amount` is small enough relative to `liq_revenue_factor`, the product `(factor * amount) / WAD` truncates to `0`.

Critically, `liquidation_inner()` in `market.move:712` only checks that the repay amount is non-zero:
```move
assert!(available_repay_coin.value() != 0, error::liquidation_zero_repay());
```

There is **no minimum repay amount** enforced.

## Impact

An attacker performing a liquidation of, say, 10,000 units of collateral can split it into 10,000 individual 1-unit liquidation calls. For each call:
- `protocol_seize_amount = int_mul(0.05, 1) = 0` (rounds down)
- `liquidator_seize_amount = 1 - 0 = 1` (liquidator gets full amount)

Compared to a single honest liquidation:
- `protocol_seize_amount = int_mul(0.05, 10000) = 500` (correct 5% fee)
- `liquidator_seize_amount = 10000 - 500 = 9500`

The protocol loses 500 units of revenue. Over all liquidations, the protocol's entire liquidation revenue stream can be drained to zero by MEV-aware liquidators who always chunk their calls.

## Code Snippet

**Fee calculation (truncating division):**
- [`float.move:63-65`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/math/sources/float.move#L63-L65): `int_mul` floors result
- [`reserve.move:175-176`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L175-L176): `protocol_seize_amount` computed with `int_mul`

**No minimum repay check:**
- [`market.move:712`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/market.move#L712): only asserts `!= 0`

## Tool used

Manual Review + Automated Analysis (Codex + Claude cross-validation)

## Recommendation

Add a minimum liquidation size check or use ceiling division for the protocol fee:

```move
// Option 1: Use ceiling multiplication for protocol fee
public fun int_mul_ceil(a: Decimal, b: u64): u64 {
    let result = a.value * (b as u256);
    let divided = result / WAD;
    if (result % WAD > 0) { safe_from_u256(divided + 1) }
    else { safe_from_u256(divided) }
}

// Option 2: Enforce minimum repay amount
assert!(available_repay_coin.value() >= MIN_LIQUIDATION_AMOUNT, error::liquidation_too_small());
```
