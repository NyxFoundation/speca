# Unbounded Token Decimals Can Trigger Protocol-Wide Abort Paths

## Summary
The protocol does not enforce an upper bound for token decimals when registering assets. If an onboarded asset has decimals above the arithmetic assumptions (18), core valuation and liquidation math aborts, making borrow/withdraw/liquidation flows for obligations touching that asset fail.

## Vulnerability Detail
`register_decimals` stores the metadata decimals value without any range check.

- `protocol::decimals_admin::register_decimals` forwards `CoinMetadata<T>` decimals directly into the registry.
- `protocol::coin_decimals_registry::register_decimals` only checks uniqueness, not bounds.

Later, runtime-critical code assumes decimals fit into u64-base power conversions:

1. `protocol::value::coin_value` computes `10u64.pow(decimals)`. For large decimals this overflows and aborts.
2. `protocol::market::liquidate_calculate_seize_ctokens` calls `math::u64::pow10_u64(decimals)`, which aborts for decimals > 18.

These valuation paths are used in obligation safety and liquidation checks (`collaterals_usd_*`, `debts_value_usd_*`, and liquidation seize calculations). Once such an asset is onboarded and referenced by an obligation, normal risk operations can be bricked by deterministic arithmetic aborts.

## Impact
A single high-decimal asset registration can cause persistent denial-of-service for critical market actions involving that asset (borrowing safety checks, withdrawals requiring safety validation, and liquidations). This can leave unhealthy positions unliquidatable and freeze risk management for affected markets.

## Code Snippet
- `contracts/protocol/sources/entry_points/admin/decimal.move:19-28`
- `contracts/protocol/sources/internal/coin_decimals_registry.move:31-43`
- `contracts/protocol/sources/internal/value.move:11-13`
- `contracts/protocol/sources/internal/market/market.move:1050-1051`
- `contracts/math/sources/u64.move:6-28`

## Tool used
Manual Review + Automated Analysis

## Recommendation
Validate decimals at registration time and reject unsupported values globally.

Suggested hardening:

```move
const MAX_SUPPORTED_DECIMALS: u8 = 18;

public(package) fun register_decimals<T>(
    registry: &mut CoinDecimalsRegistry,
    coin_meta: &CoinMetadata<T>,
): u8 {
    let type_name = type_name::with_defining_ids<T>();
    let decimals = coin::get_decimals(coin_meta);

    assert!(decimals <= MAX_SUPPORTED_DECIMALS, error::invalid_params_error());
    assert!(!table::contains(&registry.table, type_name), error::coin_decimals_registry_already_registered());

    table::add(&mut registry.table, type_name, decimals);
    decimals
}
```

Additionally, keep defensive assertions at valuation call sites to fail fast with explicit protocol errors if unexpected decimals are ever encountered.
