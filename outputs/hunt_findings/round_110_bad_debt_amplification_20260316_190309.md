After thoroughly analyzing the codebase for bad debt amplification vectors, I've traced through all the key code paths:

**Areas analyzed:**
1. **Liquidation flow** (`liquidation_inner`): Traced how `ensure_liquidate_borrow_allowed` bypasses close factor when `collateral ≤ 1.01 * debt`, and how the incentive interacts with near-bad-debt positions. The proportional capping at lines 762-771 correctly reduces repay when collateral is insufficient.

2. **emode group borrow tracking** (`update_asset_borrow`): Verified the `new_value + current_borrow - old_value` formula with `saturating_sub` correctly handles interest accrual deltas across borrow/repay/liquidation paths, even with stale pre-interest `old_value`.

3. **Reserve accounting**: Checked `repay_amount`, `liquidate_ctokens`, `burn_ctokens`, `accrue_interest` for exchange rate consistency. The exchange rate is preserved after liquidation (net rounding favors depositors by at most 1/total_supply).

4. **Interest accrual on bad debt**: Reserve debt includes uncollectable bad debt which inflates exchange rate → known as #062.

5. **ADL paths** (`handle_debt_auto_deleverage`, `handle_collateral_auto_deleverage`): No amplification - they use `liquidation_inner` with capped incentive and zero revenue factor.

6. **Precision issues in float.move**: 18-decimal fixed-point with `floor()`/`ceil()` creates sub-unit rounding that consistently favors the protocol or is neutral.

7. **Close factor bypass + incentive creating bad debt**: When a position enters the 1.01x threshold, the liquidation incentive (e.g., 5%) creates ~3.8% bad debt on the remaining position. This is the expected tradeoff for incentivizing liquidators, not a code bug.

8. **Non-collateral deposits locked in bad-debt obligations**: The `is_obligation_safe` check blocks withdrawals even for non-collateral (noted by the TODO at line 331). Related to #052.

NO_NEW_FINDINGS: All bad debt amplification vectors trace back to known issues (#062 bad_debt_not_socialized, #057 repay_fee_rate_misused, #003 spot_ema_price_inconsistency) or are expected design tradeoffs (liquidation incentive on near-bad-debt positions). The emode borrow tracking, exchange rate accounting, and proportional liquidation capping all function correctly.
