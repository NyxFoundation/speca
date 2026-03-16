# Current Finance Security Audit — Submission Index

## Table of Contents

- [Overview](#overview)
- [HIGH (3件)](#high-3件)
  - [#003 Spot/EMA Price Inconsistency](#003)
  - [#048 Close Factor Bypass](#048)
  - [#062 Bad Debt Not Socialized](#062)
- [MEDIUM (20件)](#medium-20件)
  - [ADL (4件)](#adl-4件)
  - [Oracle (2件)](#oracle-2件)
  - [Liquidation (3件)](#liquidation-3件)
  - [Deposit Limit (2件)](#deposit-limit-2件)
  - [Liquidity Mining (3件)](#liquidity-mining-3件)
  - [eMode (2件)](#emode-2件)
  - [Flash Loan / Reserve (3件)](#flash-loan--reserve-3件)
  - [Interest Accrual (1件)](#interest-accrual-1件)
- [LOW (18件)](#low-18件)
- [フィルタリング判定基準](#フィルタリング判定基準)

---

## Overview

| Severity | 件数 | PoC |
|----------|------|-----|
| HIGH | 3 | 3 |
| MEDIUM | 20 | 19 |
| LOW | 18 | 1 |
| **合計** | **41** | **23** |

---

## HIGH (3件)

<a id="003"></a>

| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 003 | Liquidator will extract excess collateral from borrowers due to spot/EMA price inconsistency | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_003_liquidation_spot_vs_ema_price.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_003_spot_ema_excess_seizure.move) |

<a id="048"></a>

| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 048 | Close Factor Bypass via Per-Debt-Type Threshold Allows Full Liquidation of Multi-Debt Obligations | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/high/report_048_close_factor_bypass_per_debt_type.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_048_close_factor_bypass_per_debt.move) |

<a id="062"></a>

| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 062 | Insolvent positions will cause loss of funds for last depositors due to unsocialized bad debt | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/high/report_062_bad_debt_not_socialized.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_062_bad_debt_not_socialized.move) |

---

## MEDIUM (20件)

### ADL (4件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 004 | ADL operator will unfairly liquidate healthy emode group users due to global debt check | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_004_adl_borrow_global_debt_check.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_004_adl_borrow_global_debt_check.move) |
| 035 | ADL Liquidation LTV Degrades to Zero, Enabling Liquidation of All Positions | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_035_adl_ltv_degrades_to_zero.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_035_adl_ltv_degrades_to_zero.move) |
| 038 | ADL Liquidation Can Abort on Zero-Collateral Obligations Due to Division by Zero | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_038_adl_zero_collateral_division_abort.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_038_adl_zero_collateral_division_abort.move) |
| 039 | ADL Liquidation Bypasses Asset Liquidation Pause Controls | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_039_adl_bypasses_liquidation_pause_control.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_039_adl_bypasses_liquidation_pause.move) |

### Oracle (2件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 009 | Asymmetric oracle deviation check allows dangerous operations during debt token price spikes | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_009_oracle_deviation_check_asymmetric.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_009_oracle_deviation_asymmetric.move) |
| 052 | Non-Collateral Withdrawal Unnecessarily Blocked by Unrelated Oracle Staleness | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_052_non_collateral_withdraw_blocked_by_unrelated_oracle.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_052_non_collateral_withdraw_blocked.move) |

### Liquidation (3件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 028 | Dust Obligations Become Unliquidatable Due to Seize Amount Flooring to Zero | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_028_dust_obligation_unliquidatable.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_028_dust_obligation_unliquidatable.move) |
| 031 | Circuit Break Blocks Liquidation, Allowing Bad Debt Accumulation | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_031_circuit_break_blocks_liquidation.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_031_circuit_break_blocks_liquidation.move) |
| 036 | Liquidation Skips min_borrow_amount Check, Creating Economically Unclearable Dust Positions | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_036_liquidation_missing_min_borrow_check.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_036_liquidation_dust_position.move) |

### Deposit Limit (2件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 032 | Deposit Limit Check Double-Subtracts cash_reserve, Allowing Limit Bypass | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_032_deposit_limit_double_subtraction.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_032_deposit_limit_bypass.move) |
| 041 | deposit_limit_breached u64 Underflow Aborts and Blocks All Deposits | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_041_deposit_limit_u64_underflow_blocks_deposits.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_041_deposit_limit_underflow.move) |

### Liquidity Mining (3件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 033 | Liquidity Mining Rewards Permanently Lost During Zero-Share Periods | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_033_liquidity_mining_zero_share_reward_loss.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_033_liquidity_mining_zero_share_reward_loss.move) |
| 034 | Borrow Reward Shares Become Stale Between User Interactions, Enabling Reward Siphoning | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_034_borrow_reward_share_staleness.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_034_borrow_reward_share_staleness.move) |
| 049b | Liquidity Mining Pools Can Be Grief-Locked by Unclaimed Obligation Trackers | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_049_liquidity_mining_close_griefing_unclaimed_obligations.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_049_liquidity_mining_close_griefing.move) |

### eMode (2件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 025 | Admin eMode Update Resets Rate Limiter State | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_025_admin_emode_resets_limiter.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_025_admin_emode_resets_limiter.move) |
| 049a | eMode Borrow Tracking Uses Stale Obligation Debt in handle_repay and liquidation_inner, Inflating Group Totals | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_049_emode_stale_borrow_repay_liquidation.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_049_emode_stale_borrow_repay_liquidation.move) |

### Flash Loan / Reserve (3件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 036b | Flash Loan Withdraw Does Not Update cash Field, Causing Stale Reserve State Within PTB | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_036_flash_loan_stale_cash_accounting.md) | — |
| 050 | Flash Loan Fees Bypass reserve_factor Split and Go Entirely to Protocol | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_050_flash_loan_fee_bypasses_reserve_factor.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_050_flash_loan_fee_bypasses_reserve_factor.move) |
| 057 | repay_fee_rate Parameter Is Used as reserve_factor in Interest Accrual | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_057_repay_fee_rate_misused_as_reserve_factor.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_057_repay_fee_rate_misused_as_reserve_factor.move) |

### Interest Accrual (1件)
| # | タイトル | レポート | PoC |
|---|---------|---------|-----|
| 044 | Withdrawal of Non-Collateral Deposits Uses Stale Exchange Rate Due to Skipped Interest Accrual | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/medium/report_044_non_collateral_interest_skip_on_withdraw.md) | [poc](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/pocs/poc_044_non_collateral_interest_skip.move) |

---

## LOW (18件)

| # | タイトル | レポート |
|---|---------|---------|
| 007 | PackageCallerCap holder will disrupt protocol operations by burning their own whitelist capability | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_007_burn_whitelist_no_admin_check.md) |
| 014 | take_revenue Does Not Accrue Interest Before Withdrawal | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_014_take_revenue_stale_interest.md) |
| 018 | Flash Loan Fee Bypass via Cross-eMode Group Selection | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_018_cross_emode_flash_loan_fee_bypass.md) |
| 020 | Zero-Mint Deposit Griefing via Truncating Division | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_020_zero_mint_deposit_griefing.md) |
| 021 | Cross-Segment Rate Limiter Reduction is Broken | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_021_cross_segment_limiter_broken.md) |
| 023 | Borrow Off-By-One Liquidity Lock | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_023_borrow_off_by_one.md) |
| 029 | Normal Liquidation Only Checks Collateral Asset Pause State, Not Debt Asset | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_029_liquidation_debt_pause_unchecked.md) |
| 035b | Pyth normalize_decimals Silently Truncates Price for High-Decimal Feeds | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_035_pyth_normalize_decimals_truncation.md) |
| 038b | ADL cancel_collateral_adl Emits Timestamp in Milliseconds Instead of Seconds | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_038_adl_cancel_collateral_timestamp_unit_inconsistency.md) |
| 044b | Liquidation Repay Path Does Not Reduce Borrow Rate-Limiter Usage | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_044_liquidation_repay_does_not_reduce_borrow_limiter.md) |
| 047 | Referral Discount Parameters Sum Unbounded | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_047_referral_discount_sum_unbounded.md) |
| 048b | Referral Code Generation Uses Single-Shot Randomness and Reverts on Collision | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_048_referral_code_generation_collision_dos.md) |
| 049c | Oracle Admin Event Uses Seconds While Delay Field and Protocol Admin Events Use Milliseconds | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_049_oracle_admin_timestamp_unit_inconsistency.md) |
| 051 | Zero price_delay_tolerance_ms Configuration Can Brick Oracle Reads | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_051_zero_oracle_delay_tolerance_bricks_price_checks.md) |
| 058 | Repay Reduces Borrow Rate Limiter by Interest-Inclusive Amount | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_058_repay_over_reduces_borrow_limiter.md) |
| 059 | Liquidation Residual Overpayment Silently Consumed as Protocol Revenue | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_059_liquidation_residual_consumed_as_revenue.md) |
| 060 | eMode Liquidation Safety Check Uses Integer Division | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_060_emode_liquidation_safety_truncation.md) |
| 061 | create_market_asset_config Missing max >= min and max > 0 Validation | [report](https://github.com/NyxFoundation/security-agent/blob/hiro/high-bug-hunting/outputs/reports/low/report_061_asset_config_missing_validation.md) |

---

## フィルタリング判定基準

### Sherlock HIGH 基準
- 直接損失: >1% AND >$10（外部条件なし、ユーザーが元本/yieldを失う）
- 管理者権限やonlyOwner不要
- 完全にexternal関数からエントリーポイント

### Skip 基準
- Admin操作が前提: #004 (ADL), #025 (eMode), #031 (circuit break admin trigger)
- Griefing / Dust: #028 (dust position, 攻撃コスト > リターン)
- 前提条件の連鎖: 2つ以上の稀な条件の同時成立

### PoC 品質基準
- 強い: 実際のtx実行で異常な結果を検証 (#048, #062, #003)
- 中程度: #[expected_failure]で想定通りのrevertを実証 (#031)
- 弱い: セットアップのみでバグ発動ステップがコメント
