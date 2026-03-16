After thorough analysis of the codebase, I've systematically examined:

1. **Min borrow enforcement in borrow path** (`market.move:413`): Correctly enforced after interest accrual
2. **Min borrow enforcement in repay path** (`market.move:470`): Correctly enforced; full repay bypasses via `has_debt()` check
3. **Liquidation path** (`market.move:774`): No min_borrow check — already known as **#036** (liquidation_min_borrow)
4. **ADL paths** (`market.move:546-677`): Both ADL functions delegate to `liquidation_inner` — same gap as #036
5. **Dust position unliquidatability**: Covered by **#028** (dust_obligation_unliquidatable)
6. **Decimal precision** (`float.move`): 18-decimal u256 math — no truncation-to-zero for any reasonable amounts
7. **Ceiling rounding in `unsafe_repay_debt_only`** (`obligation.move:177`): Correctly handles fractional debt; ceiling prevents underflow
8. **Close factor bypass** (`market.move:1006`): Small USD-value debts bypass close factor, allowing full liquidation of dust
9. **Reserve debt tracking**: Ceiling-based overpayment discrepancy is at most 1 unit per operation — acknowledged in comments, negligible
10. **Emode stale borrow tracking** (`market.move:465`): Pre-interest old_borrow_amount — already known as **#049a**
11. **`repay_on_behalf` griefing**: Min_borrow check prevents attacker from creating sub-min positions via partial repay
12. **Interest accrual on 1-unit borrows**: Full 18-decimal precision preserves interest even for smallest positions

NO_NEW_FINDINGS: The min_borrow_dust_attack angle is fully covered by known bugs #028 (dust_obligation_unliquidatable), #036 (liquidation_min_borrow), and #049a (emode_stale_borrow). The borrow and repay paths correctly enforce min_borrow after interest accrual. The close_factor_bypass_min_value mechanism handles dust liquidation. The 18-decimal fixed-point math prevents precision-loss attacks on small positions.
