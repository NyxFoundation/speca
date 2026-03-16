After thorough analysis of the ADL mechanism, liquidation flow, solvency checks, and their interactions, I've systematically examined:

1. **Reserve-level vs emode-level debt check** in `handle_debt_auto_deleverage` — Already known as `004:adl_global_debt_check`
2. **ADL bypasses `liquidation_paused`** — Already known as `039:adl_bypasses_pause`
3. **ADL LTV degrades to zero** — Already known as `035:adl_ltv_degrades`
4. **Zero collateral division** in ADL — Already known as `038:adl_zero_collateral_div`
5. **Spot vs EMA price inconsistency** in seize calculation — Already known as `003:spot_ema_price_inconsistency`
6. **Rounding direction inconsistency** between repay path (`ceil`) and liquidation path (`floor`) in `try_stop_borrow_deleverage` — The magnitude is at most 1 unit (sub-cent), not exploitable for meaningful profit
7. **Metric inconsistency** for collateral ADL stop check: `handle_withdraw` uses `total_deposit_plus_interest().ceil()` while `handle_collateral_auto_deleverage` uses `cash_plus_borrows_minus_reserves().floor()` — These are mathematically equivalent (differ only by sub-unit rounding from `exchange_rate * total_supply` vs the numerator directly)
8. **Emode borrow tracking drift** due to lazy interest accrual — Standard Compound-style design limitation, captured on-demand when obligations are touched
9. **ADL neutralization via repay+reborrow** — Requires admin to have enabled ADL first (admin precondition); only prevents future ADL (indirect risk, not direct fund loss)
10. **Close factor and bad-debt bypass interactions** with ADL parameters — Working as designed
11. **Step-function nature** of `liquidation_ltv` (hourly) and `liquidation_incentive` (daily) — By design, minor MEV optimization at boundaries

NO_NEW_FINDINGS: The ADL threshold gaming angle is thoroughly covered by existing known bugs (004, 035, 038, 039). The remaining code paths are consistent and well-designed. Minor rounding inconsistencies exist but are sub-unit magnitude and non-exploitable for >$10 loss. All novel attack vectors I identified either require admin action as precondition (disqualifying for Sherlock HIGH) or produce only indirect/speculative losses rather than direct fund loss >1%.
