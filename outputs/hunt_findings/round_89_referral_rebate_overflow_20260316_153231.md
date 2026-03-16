After thorough analysis of the referral rebate mechanism and surrounding code, here's what I examined:

1. **Referral rebate u64 arithmetic** (`referral.move:132,137`): `initial_fee * discount_bps / DENOMINATOR` — in Move, u64 overflow causes abort (not silent wrap-around). For practical fee values with max bps of 9999, overflow requires `initial_fee > 1.8 * 10^15` which is ~$1.8B for a 9-decimal token. Not realistically exploitable.

2. **Self-referral**: `try_map_referral_code` properly checks `owner != user` before binding. `track_flash_loan_usage` is always called after binding check.

3. **Rebate accounting**: `record_user_rebates` and `join_rebate_balance` are always called together in `update_user_rebate` with the exact same amounts (from coin split), so the `user_rebates_records` and `rebates` bag stay perfectly in sync.

4. **Flash loan `cash` staleness during atomic execution**: `flash_loan_withdraw` doesn't update `cash`, but `exchange_rate` uses `cash` (not `underlying_balance`), so exchange rate stays constant during flash loans. No manipulation possible.

5. **No sum validation for discount bps**: Admin can set `referrer_discount_bps + referee_discount_bps > DENOMINATOR`, but this requires admin action (fails Sherlock HIGH precondition) and the math still works (referrer gets % of remainder, not of original).

6. **Referral bypass via `repay_flash_loan` vs `repay_flash_loan_increase_referral_qualification`**: Users can skip referral fees entirely, but this only means more fee goes to the protocol — no fund loss.

7. **`increase_reserve_only` for flash loan fees**: Both `cash` and `cash_reserve` increase equally, so exchange rate is unaffected. Protocol revenue correctly isolated.

NO_NEW_FINDINGS: The referral rebate mechanism uses straightforward u64 integer arithmetic with coin splits that maintain perfect accounting between records and balances. Move's abort-on-overflow prevents silent truncation. No exploitable overflow, rounding, or accounting mismatch exists that meets Sherlock HIGH criteria (>1% direct fund loss without admin action).
