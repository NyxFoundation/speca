After thorough analysis of all the core files related to borrow index manipulation, I've traced every code path involving:

1. **Borrow index computation** (`reserve.calculate_borrow_index`, `reserve.accrue_interest`): Uses simple interest correctly, idempotent same-timestamp guard, monotonically increasing assertion.

2. **Per-obligation debt accrual** (`debt.accrue_interest`, `debt.debt()`): Correctly applies `amount * new_index / old_index`. The `debt()` function always computes up-to-date debt regardless of when obligation interest was last accrued.

3. **Interest refresh ordering** (`refresh_obligation_borrow_interest`, `refresh_obligation_assets_interest`): 
   - `handle_borrow`: refreshes all borrow interest before solvency check (collateral interest not refreshed, but this is conservative — undervalues collateral)
   - `handle_withdraw`/`liquidation`: refreshes ALL interest (both borrow and collateral)
   - `handle_repay`: refreshes only the specific debt's interest (adequate since no solvency check needed)

4. **Emode borrow tracking** (`update_asset_borrow`): Uses stale `obligation_old_borrow_amount` before interest accrual, but correctly captures interest delta in `new_value - old_value`. The drift from unupdated obligations exists but doesn't enable direct fund theft.

5. **Reserve-obligation debt consistency**: `reserve.debt` (global) and individual obligation debts are updated consistently. The `ceil()` rounding in `unsafe_repay_debt_only` vs exact Decimal subtraction in `reserve.repay_amount` produces at most 1 unit of rounding error per repay — negligible.

6. **Flash loan interaction**: Flash loans don't modify `self.cash`, only the underlying balance. Regular borrows during flash loans are prevented at the Balance level (split would abort). Sui's PTB atomicity prevents cross-transaction exploitation.

7. **Exchange rate manipulation**: No donation attack vector — excess repayments go to `cash_reserve` (cancels out in exchange_rate formula), flash loan fees go to `increase_reserve_only` (same effect).

All potential issues I found are either:
- Already in the known bugs list (057:repay_fee_rate_misused, 044:non_collateral_interest_skip)
- Design decisions (simple interest vs compound, conservative collateral valuation in borrow)
- Not exploitable for direct fund loss >1% (emode drift, rate limiter over-reduction)

NO_NEW_FINDINGS: The borrow index computation, interest accrual ordering, and debt tracking are correctly implemented. All index-to-debt computations use `debt()` with the latest reserve borrow_index for security-critical checks (solvency, liquidation eligibility). The stale obligation amounts used for emode tracking correctly capture interest deltas and cannot be exploited for direct fund theft exceeding Sherlock HIGH thresholds.
