After thorough analysis of the cross-function reentrancy angle, I've examined:

1. **Flash loan `cash` accounting**: `flash_loan_withdraw` doesn't decrement `reserve.cash`, creating a temporary stale `cash` value. However, `underlying_balance.split()` acts as a hard backstop preventing actual over-extraction. After flash loan repay, `cash` and `underlying_balance` re-sync.

2. **Interest accrual ordering in `handle_borrow`**: Only refreshes borrow interest (line 407), not collateral interest. But stale collateral exchange rates are LOWER than actual (understimate collateral value), making the safety check MORE conservative — protects the protocol, not exploitable for overborrowing.

3. **Emode tracking in borrow/repay**: The `update_asset_borrow(old, new)` reads `old` before interest accrual but `new` after. The delta `new - old` includes accrued interest. Traced through the math: this correctly updates the emode tracking to reflect the sum of all obligation-level stored amounts. No accounting inflation.

4. **Liquidation exchange rate**: Read at line 748 AFTER `refresh_obligation_assets_interest` at line 720, which accrues interest for all obligation assets. Exchange rate is fresh.

5. **Flash loan + borrow/deposit in same PTB**: Sui's balance split prevents actual fund over-extraction. Cash accounting temporarily diverges but reconciles after flash loan repay.

6. **Rate limiter cross-function**: Borrow and deposit limiters are per-emode and per-asset. No cross-function bypass possible.

7. **ADL start vs stop consistency**: ADL activation uses `reserve.debt()` (real total), ADL stop uses `emode_group.borrow_amount()` (per-emode tracking). Both are consistent with their intended scope.

NO_NEW_FINDINGS: Sui Move's linear type system eliminates traditional reentrancy. Flash loan hot-potato pattern with balance-level split checks prevents cross-function fund extraction. Interest accrual staleness in borrow/withdraw creates conservative (not permissive) safety checks. Emode delta tracking correctly accounts for interest. All known stale-state vectors are either self-correcting or fail-safe.
