After thorough analysis of all interest accrual code paths, I've examined:

1. **Reserve interest accrual** (`reserve.move:125-148`) - simple interest model, borrow index updates
2. **Obligation debt tracking** (`debt.move`) - borrow index ratio computation
3. **All major flows**: `handle_borrow`, `handle_repay`, `handle_mint`, `handle_withdraw`, `handle_liquidation`, flash loans, ADL
4. **Emode group borrow tracking** (`update_asset_borrow`) - stale old_value pattern
5. **Exchange rate calculations** and rounding in `mint_ctokens`/`burn_ctokens`
6. **Utilization rate edge cases** (> 1.0 when `cash_reserve > cash`)
7. **Rate limiter** circular buffer implementation
8. **Float/Decimal arithmetic** precision and overflow boundaries

**Findings that trace back to known bugs:**
- The stale `obligation_old_borrow_amount` in `handle_borrow` (L404), `handle_repay` (L465), and `liquidation_inner` (L717) — all read `unsafe_debt_amount()` before interest accrual → already known as `049a:emode_stale_borrow`
- `asset.repay_fee_rate()` passed as `reserve_factor` in `accrue_interest` (market.move:1025) → already known as `057:repay_fee_rate_misused`
- `cash_reserve` subtracted twice in `deposit_limit_breached` → already known as `032:deposit_limit_double_subtract`

**Edge cases examined that are NOT bugs:**
- Compounding effect from frequent `accrue_interest` calls: negligible (~9 ppb/day at normal rates)
- Stale collateral exchange rate in `handle_borrow`: conservative (undervalues collateral), protects protocol
- `util_rate > 1` when `cash_reserve > cash`: produces high but valid interest rates; extreme scenario requiring prolonged 100% utilization with no repayments
- `mint_ctokens` with 0 output: only affects sub-wei deposits, no vault inflation vector (no donation mechanism)
- Division-by-zero in liquidation with zero collateral: aborts gracefully, related to `062:bad_debt_not_socialized`
- Rounding in `unsafe_repay_debt_only` (ceil vs actual): sub-unit precision, not exploitable at scale

NO_NEW_FINDINGS: All interest accrual edge cases trace back to known bugs (049a, 057, 032) or are conservative design choices. The simple interest model, borrow index propagation, and exchange rate calculations are correctly implemented. No exploitable rounding, overflow, or state inconsistency was found outside the known issues.
