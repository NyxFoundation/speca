NO_NEW_FINDINGS: The borrow index manipulation angle is exhausted.

**Analysis covered**: All core flows (borrow, repay, liquidation, ADL) in reserve.move, debt.move, obligation.move, market.move, emode.move, interest.move, and float.move.

**Key conclusion**: The borrow index implementation is mathematically sound. Interest accrual uses correct simple-interest-per-period that compounds correctly across calls. The seemingly-stale `obligation_old_borrow_amount` reads in handle_borrow/repay/liquidation are actually intentionally correct because the emode delta tracker was itself stale for the same period. No exploitable manipulation vector exists for HIGH severity.
king via delta updates
- `asset.move` — asset configuration (repay_fee_rate)
- `float.move` — 18-decimal fixed-point math library
- Entry points: borrow.move, repay.move, liquidate.move

### Key Findings (all non-exploitable)

1. **Emode borrow tracking stale old_value**: In handle_borrow, handle_repay, and liquidation_inner, the `obligation_old_borrow_amount` is read BEFORE obligation-level interest accrual. This appears buggy but is actually **correct** — the emode tracker was itself stale for the same interest period, so the delta `(new - old_stale)` correctly captures both interest accrual and the user action.

2. **Ceiling rounding in full repays**: `unsafe_repay_debt_only` uses `.ceil()` for debt amount, causing at most 1 token per full repay drift in `reserve.debt`. Not exploitable at HIGH severity.

3. **Conservative safety check in borrow**: `handle_borrow` only refreshes borrow interest (not collateral), making the solvency check more conservative (understates collateral). This is safe by design.

4. **repay_fee_rate as reserve_factor**: Already known as #057.

### Conclusion
NO_NEW_FINDINGS: The borrow index implementation is mathematically sound. Interest accrual ordering is correct everywhere. No manipulation vector yields HIGH-severity profit.
