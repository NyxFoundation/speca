# C4 Pattern Analysis Against Current Finance Sui Move Lending Protocol

## Methodology
Filtered Code4rena dataset (22,709 issues) for High-severity lending-related issues.
Extracted 35 matching issues, grouped into unique vulnerability patterns.
Cross-referenced 13 less-common C4 patterns against Current Finance codebase.

## Pattern Analysis Results

### 1. Governance token voting power manipulation via lending
**Description:** Attacker borrows governance tokens, votes, then returns them in same block.
**Check:** NO -- Not applicable. Current Finance has no governance tokens or voting mechanisms.

### 2. Cross-chain message replay in lending bridges
**Description:** Cross-chain messages can be replayed on different chains to double-credit deposits.
**Check:** NO -- Not applicable. Current Finance is Sui-only with no cross-chain bridges.

### 3. Liquidation with stale prices during sequencer downtime (L2 specific)
**Description:** On L2s, sequencer downtime allows liquidations using outdated oracle prices.
**Check:** NO -- Not applicable. Sui has no sequencer. Pyth oracle enforces 30s max staleness in `pyth_adaptor.move:85` and `price_delay_tolerance_ms` in `user_oracle.move:67`.

### 4. Incorrect shares calculation when total supply overflows
**Description:** When ctoken total supply overflows u64, share calculations become incorrect.
**Check:** NO -- Move u64 arithmetic aborts on overflow by default. `increase_ctoken_supply` in `reserve.move:271` would abort if `total_supply + amount` overflows u64. Safe by language guarantee.

### 5. Missing validation in market creation allowing duplicate markets
**Description:** Duplicate markets for same asset can be created, fragmenting liquidity.
**Check:** NO -- Protected. `register_market` checks `!app.is_market_registered()` (market_admin.move:53). `onboard_new_asset` checks `!self.assets.supports()` (market.move:230). `support_asset` in emode checks `!group.assets.supports()` (emode.move:136).

### 6. Reward token draining via deposit/claim/withdraw cycle
**Description:** Attacker repeatedly deposits, claims rewards, withdraws to drain reward pool faster than intended.
**Check:** NO -- Protected. The `change_obligation_reward_manager_share` function (reward_manager.move:211-225) calls `update_obligation_reward_manager` BEFORE changing shares, which settles pending rewards at the old share amount. New rewards only accrue based on the updated share. The deposit/withdraw entry points correctly call reward updates with the new share AFTER the state change. Time-proportional distribution with `cumulative_rewards_per_share` pattern prevents gaming.

### 7. Interest rate model discontinuity at kink points
**Description:** Interest rate function has a discontinuity (jump) at kink utilization thresholds.
**Check:** NO -- The tri-linear model in `interest.move:42-98` is continuous. At `util_rate == mid_kink` (first branch boundary), both branches evaluate to `borrow_rate_on_mid_kink`. At `util_rate == high_kink` (second boundary), both evaluate to `borrow_rate_on_high_kink`. Verified by unit tests.

### 8. Borrow cap bypass via multiple small borrows
**Description:** Per-transaction borrow limits can be bypassed by splitting into many small borrows.
**Check:** NO -- Protected. Borrow limits are cumulative, not per-transaction:
- `emode_group_total_borrow` tracks total borrows across all obligations in `update_asset_borrow` (emode.move:183-192), checked against `emode_max_borrow_amount` (market.move:422).
- `asset_max_borrow_amount` (market.move:440) checks `reserve.debt().ceil()` which is cumulative.
- Rate limiter (`add_outflow`) accumulates across time segments (limiter.move:78-94).
- `min_borrow_amount` enforces minimum per-obligation debt (obligation.move:154-166).

### 9. Incorrect collateral factor applied after emode change
**Description:** Changing emode parameters doesn't retroactively recalculate existing positions.
**Check:** NO -- Obligations have a fixed `emode_group` set at creation (obligation.move:29, enter_market.move:50). There is no function to change an obligation's emode group. Health factor checks always use the obligation's assigned emode group settings. Admin emode parameter updates take effect immediately for all obligations in that group, which is the correct behavior for a global parameter change.

### 10. Reserve factor not applied to flash loan fees
**Description:** Flash loan fees bypass the reserve factor split, going entirely to protocol.
**Check:** KNOWN (related to #057) -- Flash loan fees in `repay_flash_loan` (reserve.move:234-254) go to `increase_reserve_only` which adds entirely to `cash_reserve` (protocol revenue). Depositors receive zero share of flash loan fees. This is by design in the current codebase, but related to the known #057 finding about `repay_fee_rate` being used as the reserve factor.

### 11. Liquidation incentive exceeding remaining collateral
**Description:** Liquidation incentive calculation produces seize amount larger than available collateral.
**Check:** NO -- Protected. In `liquidation_inner` (market.move:762-771), if `total_ctokens < seized_ctokens`, the repay amount is proportionally scaled down and `seized_ctokens` is capped at `total_ctokens`. Additionally, the admin `create_emode_params` enforces `liquidation_factor * (1 + liquidation_incentive) < 1` (emode_admin.move:93-96) to prevent overcollateralization scenarios.

### 12. Withdrawal queue manipulation
**Description:** Attacker manipulates withdrawal queue ordering to front-run other withdrawals.
**Check:** NO -- Not applicable. Current Finance has no withdrawal queue. Withdrawals are immediate via `handle_withdraw` in a single transaction.

### 13. cToken transfer breaking health factor invariant
**Description:** Direct cToken transfers between users bypass health factor checks.
**Check:** NO -- Protected by design. CTokens are held as `Balance<CToken>` inside the obligation struct (obligation.move:27), not as transferable `Coin` objects. The only way to extract ctokens is via `withdraw_ctokens` (obligation.move:96-104) which is called from `handle_withdraw` that enforces `is_obligation_safe`. Users cannot transfer ctokens directly between obligations.

## Additional C4 Patterns Checked

### First depositor / exchange rate manipulation (C4 #29, #30)
**Description:** First depositor with 1 wei, then donates to inflate exchange rate, rounding subsequent depositors to 0.
**Check:** NO -- In Sui Move, there is no way to "donate" tokens directly to the reserve. All deposits go through `mint_ctokens` which mints proportional ctokens. `deposit_underlying` is a private function only callable by `mint_ctokens` and `repay_amount`. The initial exchange rate is 1:1 (reserve.move:93-95). Safe by architecture.

### Flash loan price manipulation (C4 #2)
**Description:** Flash loans used to manipulate oracle prices for favorable borrows/liquidations.
**Check:** NO -- Current Finance uses Pyth oracle with EMA prices. The `get_price` function returns EMA price (user_oracle.move:29), not spot. EMA is resistant to single-block manipulation. Additionally, `get_price_with_check` enforces ema-spot tolerance (user_oracle.move:42-58) for borrow/withdraw operations, rejecting transactions during high volatility.

### Precision loss in share/index calculations (C4 #27)
**Description:** Converting between shares and underlying amounts causes rounding errors that compound.
**Check:** NO -- The `Decimal` type uses 18 decimal places (`WAD = 10^18`, float.move:9) which provides sufficient precision. The `ensure_decimal_value_safe` function (float.move:145-148) checks for overflow. Rounding is explicitly handled (e.g., `floor()` vs `ceil()` used appropriately in debt repayment and liquidation).

## Conclusion

No new HIGH severity vulnerabilities were identified from the C4 pattern analysis.
All 13 targeted patterns are either not applicable to the Sui Move architecture, or are properly mitigated by the protocol's design.
The only related finding (#10, flash loan fees not shared with depositors) is in the same family as the known bug #057.
