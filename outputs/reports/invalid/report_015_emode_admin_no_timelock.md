# Admin eMode Parameter Changes Take Effect Immediately Without Timelock

## Summary

All eMode parameter updates (collateral factors, liquidation thresholds, liquidation incentives, borrow weights, flash loan fees, rate limiters) take effect instantly in the same transaction. A compromised admin key can immediately shift the entire liquidation regime, force-liquidating healthy positions or enabling over-borrowing.

## Vulnerability Detail

In `emode.move:135-159`, the `update_asset_in_emode_group` function directly overwrites all eMode parameters:

```move
public fun update_asset_in_emode_group<MarketType, CoinType>(
    _: &AdminCap,
    self: &ProtocolApp,
    market: &mut Market<MarketType>,
    group: u8,
    params: NewEMode,
    ctx: &TxContext,
) {
    // ... validation ...
    let emode = market.emode_registry_mut().borrow_mut_emode(group, asset);
    emode.update(params);  // Instant update, no timelock
}
```

The `update` function (emode.move:280-311) directly writes all fields:
```move
public(package) fun update(emode: &mut EMode, params: NewEMode) {
    let collateral: &mut EModeCollateral = dynamic_field::borrow_mut(...);
    collateral.collateral_factor = collateral_factor;
    collateral.liquidation_factor = liquidation_factor;
    collateral.liquidation_incentive = liquidation_incentive;
    // ... borrow, flashloan, limiter fields ...
}
```

Notably, the ADL system *does* have a timelock mechanism (`seconds_from_now` parameter with max 3 days), demonstrating the developers considered timelocks for some features but not eMode.

## Impact

- **Instant liquidation cascade**: Admin lowers `liquidation_factor` from 0.8 to 0.5 → all positions with health factor between 0.625 and 1.0 become instantly liquidatable
- **Over-borrowing**: Admin raises `collateral_factor` from 0.75 to 0.95 → users can borrow significantly more than intended
- **Flash loan fee reset**: Admin sets `flash_loan_fee_rate` to 0 → free flash loans until noticed
- **Rate limiter wipe**: Admin updates limiter parameters → existing usage counters are reset

With a compromised admin key, an attacker could: (1) lower liquidation thresholds, (2) liquidate newly-underwater positions via a MEV bot in the same block, (3) restore thresholds — all within one transaction.

## Code Snippet

- [`emode.move:135-159`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/entry_points/admin/emode.move#L135-L159): Instant parameter update
- [`emode.move:280-311`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/emode.move#L280-L311): Direct field overwrite

## Tool used

Manual Review + Automated Analysis (Codex + Claude cross-validation)

## Recommendation

Add a timelock mechanism similar to ADL:

```move
public fun propose_emode_update<MarketType, CoinType>(
    _: &AdminCap, market: &mut Market<MarketType>,
    group: u8, params: NewEMode, delay_seconds: u64,
) {
    assert!(delay_seconds >= MIN_EMODE_TIMELOCK, error::timelock_too_short());
    // Store pending update with activation timestamp
}

public fun execute_emode_update<MarketType, CoinType>(
    _: &AdminCap, market: &mut Market<MarketType>,
    group: u8, clock: &Clock,
) {
    // Only execute if timelock has elapsed
}
```
