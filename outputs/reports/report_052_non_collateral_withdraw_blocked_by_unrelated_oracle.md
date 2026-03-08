# Non-Collateral Withdrawal Unnecessarily Blocked by Unrelated Oracle Staleness

## Summary

`handle_withdraw` unconditionally runs the full obligation safety check (`is_obligation_safe`) even when the withdrawn asset has `can_be_collateral() == false`. Since non-collateral assets contribute zero to the obligation's weighted collateral value, the safety check is mathematically guaranteed to produce the same result regardless of the withdrawal. However, the check calls `get_price_with_check` for every debt and collateral asset in the obligation, which reverts when any unrelated oracle price is stale or has EMA/spot divergence beyond tolerance. This creates a fund-lockup vector where users cannot withdraw their non-collateral deposits during oracle outages for completely unrelated assets.

## Vulnerability Detail

In `market.move:303-363`, `handle_withdraw` performs the following sequence:

```move
// line 328: remove ctokens from obligation
let ctoken = obligation.withdraw_ctokens(ctoken_amount);

// line 331: TODO comment acknowledging the issue
// TODO: if the asset is not collateral, skip obligation safety check
let is_obligation_safe = is_obligation_safe(
    self.emode_group_registry.borrow_emode_group(obligation.emode_group()),
    &self.reserves,
    &self.ema_spot_tolerance,
    obligation,
    coin_decimals_registry,
    x_oracle,
    clock,
);
assert!(is_obligation_safe, error::obligation_not_safe_after_operation());
```

`is_obligation_safe` (line 1214-1249) calls two sub-functions:

1. `debts_value_usd_non_liquidation` (line 1170-1209): Iterates over ALL debt types and calls `get_price_with_check` for each at line 1198.
2. `collaterals_usd_non_liquidation` (line 1252-1296): Iterates over ALL deposit types. At line 1280, it skips non-collateral assets (`if (!collateral_config.can_be_collateral()) { continue }`), but still calls `get_price_with_check` for all COLLATERAL assets at line 1284.

When the withdrawn asset has `can_be_collateral() == false`:
- It contributes **zero** to weighted collateral value (skipped at line 1280)
- Removing it does not change the collateral value
- The safety comparison `collateral_weighted_value >= borrow_weight_weighted_debt_value` is identical before and after withdrawal
- Yet the safety check still runs and can revert if ANY debt or collateral oracle is stale

The developers acknowledged this defect with a TODO at line 331 that was never implemented.

## Internal Pre-conditions

1. An asset must be configured with `can_be_collateral() == false` (i.e., `collateral_factor == 0`) in the user's eMode group, while still being depositable.
2. The user's obligation must also hold at least one debt or one collateral asset whose oracle can become stale.

## External Pre-conditions

1. The Pyth price feed for any of the obligation's debt or collateral assets must become stale (price not refreshed on-chain within `price_delay_tolerance_ms`), OR the EMA/spot price divergence must exceed the configured `ema_spot_tolerance` for any such asset.

## Attack Path

1. Alice creates an obligation in eMode group G.
2. Alice deposits asset X (non-collateral, `can_be_collateral = false`) and asset Y (collateral).
3. Alice borrows asset Z.
4. The Pyth price feed for asset Z stops being updated on-chain (network congestion, feed delisting, relayer downtime).
5. Alice tries to withdraw her non-collateral asset X.
6. `handle_withdraw` → `is_obligation_safe` → `debts_value_usd_non_liquidation` iterates over debt types → calls `get_price_with_check` for asset Z → `check_price` at `user.move:67` reverts with `oracle_stale_price_error`.
7. Alice's non-collateral deposit X is locked despite having zero impact on obligation health.
8. Alice cannot withdraw X until someone refreshes Z's oracle price.

## Impact

Users' non-collateral deposits are unnecessarily locked when unrelated oracle prices are stale. The lockup persists until the stale oracle is refreshed by someone submitting a fresh Pyth attestation on-chain. In extreme cases (Pyth feed permanently delisted for an asset), the lockup could be permanent — the user's non-collateral funds would be trapped indefinitely.

The severity compounds for obligations with many asset types: the more assets in an obligation, the more oracle dependencies exist, and the higher the probability that at least one oracle is stale at any given time.

## Code Snippet

- [`market.move:331-342`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L331-L342): TODO comment and unnecessary safety check on non-collateral withdrawal
- [`market.move:1170-1209`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L1170-L1209): `debts_value_usd_non_liquidation` calls `get_price_with_check` for all debt types
- [`market.move:1252-1296`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L1252-L1296): `collaterals_usd_non_liquidation` skips non-collateral assets at line 1280 but still queries oracles for collateral assets
- [`user.move:61-69`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/x_oracle/sources/entry_points/user.move#L61-L69): `check_price` reverts on stale oracle

## Tool used

Manual Review + Automated Analysis (SPECA Pipeline + Claude cross-validation)

## Recommendation

Implement the TODO at line 331 — skip the obligation safety check when the withdrawn asset is non-collateral:

```move
let name = type_name::with_defining_ids<CoinType>();
let emode_group = self.emode_group_registry.borrow_emode_group(obligation.emode_group());
let collateral_config = emode_group.borrow_emode(name).collateral();

// Only run safety check if the withdrawn asset is collateral
if (collateral_config.can_be_collateral()) {
    let is_obligation_safe = is_obligation_safe(
        emode_group,
        &self.reserves,
        &self.ema_spot_tolerance,
        obligation,
        coin_decimals_registry,
        x_oracle,
        clock,
    );
    assert!(is_obligation_safe, error::obligation_not_safe_after_operation());
};
```
