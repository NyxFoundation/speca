# Current Finance Security Audit — Submission Index

## Overview

| Severity | 件数 | PoC |
|----------|------|-----|
| HIGH | 2 | 2 |
| MEDIUM | 20 | 19 |
| LOW | 18 | 1 |
| **合計** | **40** | **22** |

---

## HIGH (2件)

| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 003 | Liquidator will extract excess collateral from borrowers due to spot/EMA price inconsistency | [report](reports/high/report_003_liquidation_spot_vs_ema_price.md) | [poc](pocs/poc_003_spot_ema_excess_seizure.move) |
| 048 | Close Factor Bypass via Per-Debt-Type Threshold Allows Full Liquidation of Multi-Debt Obligations | [report](reports/high/report_048_close_factor_bypass_per_debt_type.md) | [poc](pocs/poc_048_close_factor_bypass_per_debt.move) |

---

## MEDIUM (20件)

### ADL (4件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 004 | ADL operator will unfairly liquidate healthy emode group users due to global debt check | [report](reports/medium/report_004_adl_borrow_global_debt_check.md) | [poc](pocs/poc_004_adl_borrow_global_debt_check.move) |
| 035 | ADL Liquidation LTV Degrades to Zero, Enabling Liquidation of All Positions | [report](reports/medium/report_035_adl_ltv_degrades_to_zero.md) | [poc](pocs/poc_035_adl_ltv_degrades_to_zero.move) |
| 038 | ADL Liquidation Can Abort on Zero-Collateral Obligations Due to Division by Zero | [report](reports/medium/report_038_adl_zero_collateral_division_abort.md) | [poc](pocs/poc_038_adl_zero_collateral_division_abort.move) |
| 039 | ADL Liquidation Bypasses Asset Liquidation Pause Controls | [report](reports/medium/report_039_adl_bypasses_liquidation_pause_control.md) | [poc](pocs/poc_039_adl_bypasses_liquidation_pause.move) |

### Oracle (2件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 009 | Asymmetric oracle deviation check allows dangerous operations during debt token price spikes | [report](reports/medium/report_009_oracle_deviation_check_asymmetric.md) | [poc](pocs/poc_009_oracle_deviation_asymmetric.move) |
| 052 | Non-Collateral Withdrawal Unnecessarily Blocked by Unrelated Oracle Staleness | [report](reports/medium/report_052_non_collateral_withdraw_blocked_by_unrelated_oracle.md) | [poc](pocs/poc_052_non_collateral_withdraw_blocked.move) |

### Liquidation (3件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 028 | Dust Obligations Become Unliquidatable Due to Seize Amount Flooring to Zero | [report](reports/medium/report_028_dust_obligation_unliquidatable.md) | [poc](pocs/poc_028_dust_obligation_unliquidatable.move) |
| 031 | Circuit Break Blocks Liquidation, Allowing Bad Debt Accumulation | [report](reports/medium/report_031_circuit_break_blocks_liquidation.md) | [poc](pocs/poc_031_circuit_break_blocks_liquidation.move) |
| 036 | Liquidation Skips min_borrow_amount Check, Creating Economically Unclearable Dust Positions | [report](reports/medium/report_036_liquidation_missing_min_borrow_check.md) | [poc](pocs/poc_036_liquidation_dust_position.move) |

### Deposit Limit (2件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 032 | Deposit Limit Check Double-Subtracts `cash_reserve`, Allowing Limit Bypass | [report](reports/medium/report_032_deposit_limit_double_subtraction.md) | [poc](pocs/poc_032_deposit_limit_bypass.move) |
| 041 | `deposit_limit_breached` u64 Underflow Aborts and Blocks All Deposits | [report](reports/medium/report_041_deposit_limit_u64_underflow_blocks_deposits.md) | [poc](pocs/poc_041_deposit_limit_underflow.move) |

### Liquidity Mining (3件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 033 | Liquidity Mining Rewards Permanently Lost During Zero-Share Periods | [report](reports/medium/report_033_liquidity_mining_zero_share_reward_loss.md) | [poc](pocs/poc_033_liquidity_mining_zero_share_reward_loss.move) |
| 034 | Borrow Reward Shares Become Stale Between User Interactions, Enabling Reward Siphoning | [report](reports/medium/report_034_borrow_reward_share_staleness.md) | [poc](pocs/poc_034_borrow_reward_share_staleness.move) |
| 049b | Liquidity Mining Pools Can Be Grief-Locked by Unclaimed Obligation Trackers | [report](reports/medium/report_049_liquidity_mining_close_griefing_unclaimed_obligations.md) | [poc](pocs/poc_049_liquidity_mining_close_griefing.move) |

### eMode (2件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 025 | Admin eMode Update Resets Rate Limiter State | [report](reports/medium/report_025_admin_emode_resets_limiter.md) | [poc](pocs/poc_025_admin_emode_resets_limiter.move) |
| 049a | eMode Borrow Tracking Uses Stale Obligation Debt in `handle_repay` and `liquidation_inner`, Inflating Group Totals | [report](reports/medium/report_049_emode_stale_borrow_repay_liquidation.md) | [poc](pocs/poc_049_emode_stale_borrow_repay_liquidation.move) |

### Flash Loan / Reserve (3件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 036b | Flash Loan Withdraw Does Not Update `cash` Field, Causing Stale Reserve State Within PTB | [report](reports/medium/report_036_flash_loan_stale_cash_accounting.md) | — |
| 050 | Flash Loan Fees Bypass `reserve_factor` Split and Go Entirely to Protocol, Depriving Depositors of Fee Revenue | [report](reports/medium/report_050_flash_loan_fee_bypasses_reserve_factor.md) | [poc](pocs/poc_050_flash_loan_fee_bypasses_reserve_factor.move) |
| 057 | `repay_fee_rate` Parameter Is Used as `reserve_factor` in Interest Accrual — No Repay Fee Is Ever Charged | [report](reports/medium/report_057_repay_fee_rate_misused_as_reserve_factor.md) | [poc](pocs/poc_057_repay_fee_rate_misused_as_reserve_factor.move) |

### Interest Accrual (1件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 044 | Withdrawal of Non-Collateral Deposits Uses Stale Exchange Rate Due to Skipped Interest Accrual | [report](reports/medium/report_044_non_collateral_interest_skip_on_withdraw.md) | [poc](pocs/poc_044_non_collateral_interest_skip.move) |

---

## LOW (18件)

| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 007 | PackageCallerCap holder will disrupt protocol operations by burning their own whitelist capability | [report](reports/low/report_007_burn_whitelist_no_admin_check.md) | — |
| 014 | take_revenue Does Not Accrue Interest Before Withdrawal | [report](reports/low/report_014_take_revenue_stale_interest.md) | — |
| 018 | Flash Loan Fee Bypass via Cross-eMode Group Selection | [report](reports/low/report_018_cross_emode_flash_loan_fee_bypass.md) | — |
| 020 | Zero-Mint Deposit Griefing via Truncating Division | [report](reports/low/report_020_zero_mint_deposit_griefing.md) | — |
| 021 | Cross-Segment Rate Limiter Reduction is Broken | [report](reports/low/report_021_cross_segment_limiter_broken.md) | — |
| 023 | Borrow Off-By-One Liquidity Lock | [report](reports/low/report_023_borrow_off_by_one.md) | — |
| 029 | Normal Liquidation Only Checks Collateral Asset Pause State, Not Debt Asset | [report](reports/low/report_029_liquidation_debt_pause_unchecked.md) | [poc](pocs/poc_029_liquidation_debt_pause_bypass.move) |
| 035b | Pyth normalize_decimals Silently Truncates Price for High-Decimal Feeds | [report](reports/low/report_035_pyth_normalize_decimals_truncation.md) | — |
| 038b | ADL cancel_collateral_adl Emits Timestamp in Milliseconds Instead of Seconds | [report](reports/low/report_038_adl_cancel_collateral_timestamp_unit_inconsistency.md) | — |
| 044b | Liquidation Repay Path Does Not Reduce Borrow Rate-Limiter Usage | [report](reports/low/report_044_liquidation_repay_does_not_reduce_borrow_limiter.md) | — |
| 047 | Referral Discount Parameters Sum Unbounded — Protocol Can Lose Nearly All Flash Loan Fee Revenue | [report](reports/low/report_047_referral_discount_sum_unbounded.md) | — |
| 048b | Referral Code Generation Uses Single-Shot Randomness and Reverts on Collision | [report](reports/low/report_048_referral_code_generation_collision_dos.md) | — |
| 049c | Oracle Admin Event Uses Seconds While Delay Field and Protocol Admin Events Use Milliseconds | [report](reports/low/report_049_oracle_admin_timestamp_unit_inconsistency.md) | — |
| 051 | Zero `price_delay_tolerance_ms` Configuration Can Brick Oracle Reads and Lending Flows | [report](reports/low/report_051_zero_oracle_delay_tolerance_bricks_price_checks.md) | — |
| 058 | Repay Reduces Borrow Rate Limiter by Interest-Inclusive Amount, Eroding Safety Margin | [report](reports/low/report_058_repay_over_reduces_borrow_limiter.md) | — |
| 059 | Liquidation Residual Overpayment Silently Consumed as Protocol Revenue | [report](reports/low/report_059_liquidation_residual_consumed_as_revenue.md) | — |
| 060 | eMode Liquidation Safety Check Uses Integer Division, Allowing Off-by-One bps Configurations | [report](reports/low/report_060_emode_liquidation_safety_truncation.md) | — |
| 061 | `create_market_asset_config` Missing `max >= min` and `max > 0` Validation | [report](reports/low/report_061_asset_config_missing_validation.md) | — |

---

## PoC Helper

| ファイル | 用途 |
|---------|------|
| [poc_helper_x_oracle_divergent.move](pocs/poc_helper_x_oracle_divergent.move) | Spot/EMA乖離テスト用共通ヘルパー (poc_003, poc_009が依存) |

---

## Notes

- report_036 は2件別テーマ (liquidation dust / flash loan stale cash) — 番号重複だがそれぞれ独立
- report_049 は3件別テーマ (emode stale borrow / liquidity mining griefing / oracle timestamp) — 番号重複だがそれぞれ独立
- PoC未作成は report_036b (flash loan stale cash) の1件のみ — PTB内の一時的状態のため単体テストでの再現が困難
- poc_034 は2ファイル存在: `poc_034_borrow_reward_share_staleness.move` (正) + `poc_034_borrow_reward_staleness.move` (重複)
- 全PoC配置先: `contracts/protocol/tests/integration/test_cases/`
- テスト実行: `sui move test --filter poc_`
