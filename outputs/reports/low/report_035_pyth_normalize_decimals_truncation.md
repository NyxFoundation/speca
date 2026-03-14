### Attacker will borrow against inflated collateral valuation due to silent price truncation for high-decimal Pyth feeds

### Summary

Integer division truncation in `normalize_decimals` when `price_decimals > 9` will cause incorrect collateral valuations for the protocol as an attacker will deposit tokens whose truncated price is higher than the true value and borrow against the inflated collateral.

### Root Cause

In [`pyth_adaptor.move:67-79`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/x_oracle/sources/internal/pyth_adaptor.move#L67-L79) the `normalize_decimals` function performs integer division when a Pyth price feed has more than 9 decimal places, silently destroying price precision:

```move
fun normalize_decimals(price_value: u64, price_decimals: u8): u64 {
    let formatted_decimals = price_feed::decimals();  // = 9

    let price_value_with_formatted_decimals = if (price_decimals < formatted_decimals) {
        price_value * pow10_u64(formatted_decimals - price_decimals)
    } else {
        // This should rarely happen, since formatted_decimals is 9 and price_decimals is usually smaller than 8
        price_value / pow10_u64(price_decimals - formatted_decimals)  // INTEGER DIVISION TRUNCATION
    };
    assert!(price_value_with_formatted_decimals > 0, oracle_error::pyth_price_decimals_too_large());

    price_value_with_formatted_decimals
}
```

The `assert!(... > 0)` check only catches complete zeroing, not partial precision loss. Additionally, [`register_pyth_feed`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/x_oracle/sources/internal/pyth_adaptor.move#L105-L126) (line 105-126) provides no validation against registering feeds with `price_decimals > 9`.

### Internal Pre-conditions

1. [Admin needs to call `register_pyth_feed` to register] a Pyth feed with more than 9 decimal places (`expo < -9`).

### External Pre-conditions

None.

### Attack Path

1. Admin registers a Pyth feed with `expo = -12` (12 decimal places).
2. `normalize_decimals` divides `price_value` by `10^3 = 1000`, losing 3 digits of precision.
3. Truncated price rounds relative to true value (e.g., `123456789123` becomes `123456789`).
4. Attacker deposits token whose truncated price is higher than true value.
5. Attacker calls `borrow` against the inflated collateral valuation.
6. Liquidation calculations also use truncated price, allowing undercollateralized positions to persist.

### Impact

The protocol suffers incorrect collateral valuations when any Pyth feed with more than 9 decimal places is onboarded. For a feed with `expo = -18` (common for Ethereum-bridged tokens), division by `10^9` can reduce a meaningful price to nearly zero or a wildly inaccurate value. The attacker gains the ability to borrow high-value assets against inflated collateral.

### PoC

_No PoC provided._

### Mitigation

Add a maximum decimals check in `register_pyth_feed` or `normalize_decimals`:

```move
fun normalize_decimals(price_value: u64, price_decimals: u8): u64 {
    let formatted_decimals = price_feed::decimals();

    // Reject feeds that would lose significant precision
    assert!(
        price_decimals <= formatted_decimals + 2,
        oracle_error::pyth_price_decimals_too_large()
    );

    let price_value_with_formatted_decimals = if (price_decimals < formatted_decimals) {
        price_value * pow10_u64(formatted_decimals - price_decimals)
    } else {
        price_value / pow10_u64(price_decimals - formatted_decimals)
    };
    assert!(price_value_with_formatted_decimals > 0, oracle_error::pyth_price_decimals_too_large());

    price_value_with_formatted_decimals
}
```
