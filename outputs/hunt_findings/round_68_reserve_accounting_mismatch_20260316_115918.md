After a thorough analysis of the reserve accounting in the Current Finance protocol, I've examined:

1. **Reserve debt vs obligation debt sync**: The borrow index mechanism ensures both track interest consistently using the same `(1 + rate * time)` factor. Rounding differences are sub-1-unit per operation.

2. **Cash tracking consistency**: `self.cash` stays synchronized with `underlying_balance` across all operations. The flash loan temporarily desynchronizes them (flash_loan_withdraw doesn't update cash), but the atomic PTB execution ensures re-sync.

3. **Cash_reserve tracking**: Protocol revenue is correctly segregated in all paths (interest accrual, liquidation seizure, flash loan fees, excess repay).

4. **Exchange rate preservation**: All operations (mint, burn, borrow, repay, liquidation) either preserve or slightly increase the exchange rate. Rounding via `int_mul` (floor) consistently favors existing depositors.

5. **Emode borrow tracking**: The `update_asset_borrow(old, new)` pattern correctly captures pre-interest vs post-interest deltas across borrow, repay, and liquidation flows.

6. **Liquidation residual**: The discarded `_residual` in `liquidation_inner` is always 0 or negligible because the repay amount is pre-capped to `ceil(obligation_debt)`.

Every potential mismatch I identified is either:
- Sub-1-unit rounding in the protocol-safe direction (not exploitable for >1% loss)
- Already a known bug (057: repay_fee_rate_misused, 050: flash_loan_fee_bypass_reserve, 044: non_collateral_interest_skip)
- A design decision (emode totals lag behind accrued interest for inactive obligations)

NO_NEW_FINDINGS: Reserve accounting is fundamentally sound. All rounding consistently favors the protocol/depositors. The cash/debt/cash_reserve tracking is consistent across borrow, repay, liquidation, flash loan, and interest accrual flows. Sub-1-unit precision losses cannot be amplified to meet the >1% / >$10 HIGH threshold.
