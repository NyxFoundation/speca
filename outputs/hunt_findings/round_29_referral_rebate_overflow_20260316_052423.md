After thorough analysis of the referral rebate system, I've traced all code paths and arithmetic:

**Referral rebate system analysis:**

1. **Overflow in `initial_fee * discount_bps` (referral.move:132,137):** In Sui Move, u64 overflow aborts the transaction rather than wrapping, so this would be DoS, not fund theft. Additionally, with realistic token supplies (even 18-decimal tokens), the fee values needed to trigger overflow are impractical (~4.6e16 with 400 bps).

2. **Combined bps validation (referral.move:250-251):** `referrer_discount_bps` and `referee_discount_bps` are validated individually as `< 10000` but not combined. However, the calculation is sequential (referee from full fee, referrer from remainder), so the protocol always retains a positive amount. And this requires admin action — fails Sherlock's "no admin precondition" criterion.

3. **Self-referral prevention:** Properly enforced in `try_map_referral_code` (line 225) before codes reach `track_flash_loan_usage`. Binding is permanent and code ownership is immutable.

4. **Balance accounting invariant:** `record_user_rebates` and `join_rebate_balance` are always called atomically in `update_user_rebate`, maintaining the invariant that `sum(user records) == Bag balance` per CoinType. No path allows records to diverge from actual balances.

5. **Claim correctness:** `claim_rebates` atomically removes from records and splits from shared balance. No double-claim possible since the VecMap entry is removed.

6. **Circular referrals (A refers B, B refers A):** Possible but is a common referral system limitation, not a security vulnerability. The discounts are within configured bounds.

7. **Flash loan repay check (market.move:837):** Uses strict `==` check for `amount + fee`, preventing overpay/underpay edge cases.

NO_NEW_FINDINGS: The referral rebate system has sound accounting invariants — all u64 arithmetic that could theoretically overflow would abort (DoS not theft) and requires impractical values; balance tracking between user records and the shared Bag is always atomic; self-referral is properly prevented; and admin-only parameter changes don't meet Sherlock HIGH criteria.
