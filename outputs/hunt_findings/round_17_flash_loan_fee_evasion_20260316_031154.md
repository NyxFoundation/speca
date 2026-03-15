After thorough analysis of the flash loan code paths, I've traced every angle systematically:

**Angles analyzed:**

1. **`flash_loan_withdraw` doesn't update `self.cash`** — During a flash loan, `self.cash` is stale (higher than actual `underlying_balance`). However, no other operations (deposit, withdraw, borrow, repay) check `flash_loan_ongoing`. I verified that:
   - Exchange rate uses `self.cash` (unchanged), so it's NOT inflated
   - Borrow check `self.cash - cash_reserve > amount` might pass, but actual `underlying_balance.split()` enforces the real constraint and would abort
   - Deposit limit check is more restrictive (not less) with stale cash
   - In Sui, PTBs are atomic, so other users' transactions can't observe the intermediate state

2. **Emode group shopping** — User freely picks `emode_group` parameter to get the cheapest flash loan fee rate. This is by design since admin configures per-group rates.

3. **Fee rounding via `int_mul`** — Maximum rounding savings is <1 token unit. For USDC, that's <$0.000001. Splitting loans doesn't help since each pays minimum fee=1. Protected by `assert!(fee != 0)`.

4. **Referral rebate drain** — After rebates, the code asserts `fee_coin.value() != 0`. Even with max discount settings (9999/10000 each), remaining fee is always >= 1 when original fee >= 1 due to integer division truncation.

5. **Self-referral** — `try_map_referral_code` enforces `owner != user`. Mutual referral (A→B and B→A) is possible but only yields ~14% total rebate, not a HIGH severity loss.

6. **Flash loan borrowing from protocol reserves** — Comment says "allow flash loan to borrow reserves" (`amount < self.cash` vs normal `cash - cash_reserve > amount`). Since hot potato ensures atomic repayment, this is safe.

7. **Interaction with interest accrual** — `util_rate` uses `self.cash` (unchanged during flash loan), so interest calculations are unaffected.

8. **Known bugs verified:** 050 (fee goes entirely to `cash_reserve`, not depositors) and 057 (`repay_fee_rate` used as `reserve_factor` in `accrue_interest` at market.move:1025) are both confirmed present but already on the known list.

NO_NEW_FINDINGS: Flash loan fee mechanism is well-designed — hot potato pattern ensures atomic repayment, exact equality check prevents underpayment, minimum fee assertion prevents zero-fee loans, post-rebate check prevents complete fee evasion, and self-referral checks prevent rebate abuse. All exploitable angles (050, 057) are already known.
