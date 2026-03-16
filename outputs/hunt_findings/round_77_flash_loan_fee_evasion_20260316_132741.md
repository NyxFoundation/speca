NO_NEW_FINDINGS: The flash loan fee evasion angle is exhausted after thorough analysis of all code paths. Key defenses (hot potato pattern, exact repayment check, non-zero fee assertions, self-referral block, reentrancy lock) are all intact. The `flash_loan_withdraw` not updating `self.cash` is intentional and unexploitable due to `underlying_balance.split()` acting as the real safety check. Referral qualification inflation via flash loan amounts is at most Medium severity. Known bugs #050 and #057 already cover the main flash loan fee issues.
ay_flash_loan` in same PTB — prevents non-repayment
2. **Exact equality check**: `coin.value() == inner.amount() + fee` at market.move:837 — prevents underpayment
3. **Non-zero fee assertion**: `assert!(fee != 0)` at market.move:814 — prevents zero-fee loans
4. **Post-rebate fee check**: `assert!(fee_coin.value() != 0)` at market.move:851 — prevents full rebate via referral
5. **Self-referral blocked**: `assert!(owner != user)` at referral.move:225
6. **Reentrancy lock**: `flash_loan_lock` per asset prevents nested flash loans on same asset

## Angles Investigated But Not Exploitable

### 1. `flash_loan_withdraw` not updating `self.cash`
- `flash_loan_withdraw` (reserve.move:318-324) does NOT decrement `self.cash`, causing stale accounting during flash loan
- Exchange rate uses stale `cash`, appearing unchanged during flash loan
- NOT exploitable: `underlying_balance.split()` is the true balance check and would revert on insufficient funds
- Design is intentional — flash loan is atomic, cash returns by end of PTB

### 2. EMode group selection for lower fee rate
- User can choose any `emode_group` parameter in `borrow_flash_loan`
- Different groups can have different `flash_loan_fee_rate` for same asset
- NOT a bug: all fee rates are admin-configured; this is a design feature of emode groups

### 3. Referral qualification inflation via flash loans
- `repay_flash_loan_increase_referral_qualification` tracks `loan.loan_amount()` (principal, not fee) toward `accumulated_deposit_only_usd`
- Allows cheaply reaching `referrer_deposit_usd_threshold` to create referral codes
- Impact: at most Medium — loss limited to discount % of fees (5-9% of 0.1% fee = negligible per tx)
- Does not meet Sherlock HIGH criteria (no >1% direct fund loss)

### 4. Referral discount stacking
- `referee_discount_bps` and `referrer_discount_bps` validated independently (`< 10000` each)
- Combined could theoretically be high, but admin controls these values and post-rebate non-zero check prevents full evasion

## Already Known Related Bugs
- #050: `flash_loan_fee_bypass_reserve` — fee goes only to `cash_reserve` (protocol), not to depositors via exchange rate
- #057: `repay_fee_rate_misused` — fee rate misuse in repayment context
