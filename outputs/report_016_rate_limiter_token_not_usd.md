# Rate Limiter Uses Raw Token Amounts Instead of USD Value

## Summary

The rate limiter tracks outflow in raw token units (`u64`) rather than USD-denominated value. This creates inconsistent economic protection: a limit of 1,000,000 means vastly different things for BTC (~$65B) vs USDC (~$1M), allowing disproportionate value extraction for high-priced assets.

## Vulnerability Detail

In `limiter.move:78-94`, `add_outflow` accepts a raw `u64` value:

```move
public(package) fun add_outflow(
    limiter: &mut Limiter,
    now: u64,
    value: u64,  // Raw token amount, no USD conversion
) {
    let curr_outflow = limiter.count_current_outflow(now);
    assert!(curr_outflow + value <= limiter.outflow_limit, error::outflow_reach_limit_error());
    // ...
    segment.value = segment.value + value;
}
```

All callers pass raw token amounts:
```move
// market.move:349 (withdraw)
emode.borrow_mut_deposit_limiter().add_outflow(now, deposit.value());

// market.move:402 (borrow)
emode.borrow_mut_borrow_limiter().add_outflow(now, borrow_amount);
```

The `outflow_limit` is set by admin via `NewEMode` parameters and is also a raw `u64`. There is no price oracle integration in the limiter.

## Impact

- **High-value assets under-protected**: If the admin sets a limit thinking in "number of tokens," a limit of 1000 BTC allows ~$65M of outflow while 1000 USDC allows only $1000
- **Admin operational burden**: The admin must manually account for price differences and decimal differences when configuring limits, and must update limits when asset prices change significantly
- **Price volatility gap**: During rapid price movements, the effective USD protection changes without any limit adjustment

The per-eMode-group-per-asset configuration does allow per-asset tuning, but requires constant manual adjustment to maintain consistent USD-denominated protection across assets.

## Code Snippet

- [`limiter.move:78-94`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/limiter.move#L78-L94): Raw `u64` value tracking
- [`market.move:349`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/market.move#L349): Deposit limiter with raw value
- [`market.move:402`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/market.move#L402): Borrow limiter with raw value

## Tool used

Manual Review + Automated Analysis (Codex + Claude cross-validation)

## Recommendation

Convert token amounts to USD before tracking:

```move
public(package) fun add_outflow_usd(
    limiter: &mut Limiter,
    now: u64,
    token_amount: u64,
    price: Decimal,
    decimals: u8,
) {
    let usd_value = price.int_mul(token_amount) / pow10(decimals);
    add_outflow(limiter, now, usd_value);
}
```
