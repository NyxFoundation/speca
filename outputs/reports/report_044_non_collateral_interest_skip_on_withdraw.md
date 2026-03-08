# Withdrawal of Non-Collateral Deposits Uses Stale Exchange Rate Due to Skipped Interest Accrual

## Summary

`refresh_obligation_assets_interest` skips calling `accrue_interest` for deposited assets where `can_be_collateral()` returns false. When a user withdraws such a non-collateral deposit, `burn_ctokens` uses a stale exchange rate, causing the user to receive fewer underlying tokens than entitled.

## Root Cause

In [`market.move:858-886`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L858-L886), `refresh_obligation_assets_interest` iterates over the obligation's deposit types and calls `accrue_interest` for each. However, at line 882, assets where `can_be_collateral()` is false are skipped:

```move
// cannot be collateral, ignore
if (!collateral_settings.can_be_collateral()) { continue };

accrue_interest<MarketType>(name, reserves, asset.asset_config(), asset.interest_model(), now);
```

When `handle_withdraw` (line 308-363) calls this function at line 326, interest is not accrued for the withdrawn non-collateral asset. The subsequent `reserve.burn_ctokens` at line 345 uses the stale exchange rate, which undervalues the user's cTokens.

The exchange rate formula is `(cash + debt - cash_reserve) / total_supply`. Without interest accrual, `debt` is understated (interest not added to outstanding borrows) and `cash_reserve` is understated (protocol revenue not accounted). The net effect is a lower-than-correct exchange rate, meaning fewer underlying tokens per cToken.

## Internal Pre-conditions

1. An asset must be configured with `can_be_collateral() == false` (i.e., `liquidation_factor == 0`) in the user's eMode group.
2. The asset must have active borrows generating interest (otherwise exchange rate is unchanged).
3. Sufficient time must pass since the last interaction with the reserve (deposit, borrow, repay by any user) so the stale interest is material.

## External Pre-conditions

None. This is a code logic error in the interest accrual control flow.

## Attack Path

1. Admin configures an eMode group where Asset X has `can_be_collateral = false` (liquidation_factor = 0, but deposits and borrows are permitted).
2. Alice deposits Asset X via `handle_mint` (line 274 correctly calls `accrue_interest`). She receives cTokens at the correct exchange rate.
3. Time passes. Other users borrow Asset X, generating interest that increases the reserve's `debt` and `cash_reserve`.
4. Alice calls `handle_withdraw` for Asset X. `refresh_obligation_assets_interest` at line 326 skips `accrue_interest` for Asset X because it is non-collateral (line 882).
5. `burn_ctokens` at line 345 uses the un-accrued exchange rate, which is lower than the true rate.
6. Alice receives fewer underlying tokens than she is entitled to. The "missing" interest effectively remains in the reserve, benefiting other depositors or protocol reserves.

## Impact

Depositors of non-collateral assets lose accrued interest on withdrawal. The magnitude scales with:
- The interest rate on the asset
- The time since the reserve was last touched by any operation
- The size of the withdrawal

For assets with high utilization and infrequent interactions, the loss can be material. However, the practical impact is mitigated by the fact that `accrue_interest` is triggered by many operations (deposit, borrow, repay by any user on that reserve), so a reserve that has active borrows generating interest is likely also being frequently touched. The worst case occurs for non-collateral assets with few market participants and long periods between any interaction.

## PoC

Code inspection confirms the vulnerability:

1. `handle_withdraw` (`market.move:308-363`) calls `refresh_obligation_assets_interest` at line 326.
2. `refresh_obligation_assets_interest` (`market.move:858-886`) at line 882: `if (!collateral_settings.can_be_collateral()) { continue }` — skips `accrue_interest` for non-collateral assets.
3. `handle_withdraw` loads the reserve at line 344 and calls `reserve.burn_ctokens` at line 345, which uses the current (stale) `exchange_rate()`.
4. Compare with `handle_mint` (`market.move:262-294`) at line 274: `let reserve = accrue_interest<MarketType>(...)` — deposits correctly accrue interest first.
5. The asymmetry between mint (always accrues) and withdraw (skips non-collateral) creates a systematic loss for non-collateral depositors.

## Mitigation

Remove the `can_be_collateral()` check from `refresh_obligation_assets_interest`, or add a separate `accrue_interest` call in `handle_withdraw` before `burn_ctokens`:

```move
// In refresh_obligation_assets_interest, remove the early continue:
// if (!collateral_settings.can_be_collateral()) { continue };
// Always accrue interest for all deposited assets
accrue_interest<MarketType>(name, reserves, asset.asset_config(), asset.interest_model(), now);
```

Alternatively, add a direct interest accrual in `handle_withdraw` before line 344:

```move
let asset = self.assets.load_by_type(name);
accrue_interest<MarketType>(name, &mut self.reserves, asset.asset_config(), asset.interest_model(), now);
let reserve = self.reserves.load_mut_by_type(name);
let deposit = reserve.burn_ctokens<MarketType, CoinType>(ctoken.into_coin(ctx));
```
