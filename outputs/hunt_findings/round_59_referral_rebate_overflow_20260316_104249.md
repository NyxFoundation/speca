I've thoroughly analyzed the referral rebate system across all relevant code paths. Let me summarize my findings:

**Code analyzed:**
- `referral.move` — core referral logic (track_flash_loan_usage, claim_rebates, qualification)
- `market.move` — flash loan borrow/repay with referral integration
- `flash_loan.move` — entry points (repay_flash_loan, repay_flash_loan_increase_referral_qualification)
- `reserve.move` — flash_loan_withdraw, repay_flash_loan, increase_reserve_only
- `emode.move` — flash loan fee rate config
- `float.move` — fixed-point math (u256 intermediates)

**Angles investigated:**
1. **u64 overflow in rebate calculation** (`initial_fee * referee_discount_bps`): Would only overflow at ~$1.8B+ fee amounts; causes abort (no fund loss), and users can still use basic repay path without referral.
2. **Missing combined bps validation**: `referrer_discount_bps + referee_discount_bps` not checked against DENOMINATOR, but requires admin action (disqualifies from HIGH).
3. **Flash loan qualification bypass**: `track_referral` uses loan amount (not fee) to inflate `accumulated_deposit_only_usd`. But the function is explicitly named `repay_flash_loan_increase_referral_qualification` — intentional design.
4. **Self-referral bypass**: `track_flash_loan_usage` doesn't check `who != referer`, but `try_map_referral_code` prevents self-binding. Using two addresses is inherent to blockchain.
5. **Rebate accounting mismatch**: Verified that `record_user_rebates` amounts exactly match `join_rebate_balance` amounts — no desync possible.
6. **Reserve accounting after rebate**: Verified that `underlying_balance` correctly tracks loan principal repayment, and `cash`/`cash_reserve` correctly increase by post-rebate fee only.
7. **Integer truncation in rebate**: Dust lost to truncation stays in `fee_coin` and goes to protocol reserve — no fund loss.

NO_NEW_FINDINGS: The referral rebate system is tightly scoped to flash loan fees only, uses consistent accounting between recorded amounts and actual balances, and the fee calculation uses u256 intermediates (float.move) preventing overflow. The u64 multiplication in rebate calculation (`initial_fee * bps`) can theoretically overflow but only at unrealistic amounts and causes a safe abort. No path leads to direct fund loss meeting Sherlock HIGH criteria without admin preconditions.
