# Pyth normalize_decimals Silently Truncates Price for High-Decimal Feeds

## Summary

The `normalize_decimals` function in `pyth_adaptor.move` performs integer division when a Pyth price feed has more than 9 decimal places, silently destroying price precision. The only guard (`> 0`) fails to catch partial precision loss, enabling incorrect collateral valuations.

## Vulnerability Detail

When `price_decimals > formatted_decimals` (9), the function divides the price value by `pow10(price_decimals - 9)`, truncating all sub-unit precision:

```move
// pyth_adaptor.move:67-79
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

The `register_pyth_feed` function (line 105-126) provides no validation or warning against registering feeds with `price_decimals > 9`. The admin entry point blindly passes through without checking feed decimal characteristics.

For a Pyth feed with `expo = -12` (12 decimal places), a price value of `123456789123` (representing $0.123456789123) would be divided by `10^3 = 1000`, producing `123456789` — losing 3 digits of precision. For feeds with `expo = -18` (common for Ethereum-bridged tokens), division by `10^9` can reduce a meaningful price to nearly zero or a wildly inaccurate value.

## Internal Pre-conditions

1. A Pyth feed with more than 9 decimal places (`expo < -9`) must be registered via `register_pyth_feed`.

## External Pre-conditions

None.

## Attack Path

1. Admin registers a Pyth feed with `expo = -12` (12 decimal places).
2. `normalize_decimals` divides `price_value` by `10^3 = 1000`, losing 3 digits of precision.
3. Truncated price may round UP or DOWN relative to true value.
4. Attacker deposits token whose truncated price is higher than true value.
5. Borrows high-value assets against inflated collateral valuation.
6. Liquidation calculations also use truncated price, allowing undercollateralized positions to persist.

## Impact

If any Pyth feed with more than 9 decimal places is onboarded:
- Price precision is silently destroyed, leading to incorrect collateral valuations
- An attacker could deposit a token whose truncated price is rounded UP relative to its true value, then borrow high-value assets against the inflated collateral
- Liquidation calculations would use the truncated price, potentially allowing under-collateralized positions to persist
- The `assert!(... > 0)` check only catches complete zeroing, not 99.9% precision loss

## Code Snippet

- `contracts/x_oracle/sources/internal/pyth_adaptor.move:67-79` — `normalize_decimals` truncation
- `contracts/x_oracle/sources/internal/pyth_adaptor.move:105-126` — `register_pyth_feed` missing decimal validation

## Tool used

Manual Review + Automated Analysis

## Mitigation

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
