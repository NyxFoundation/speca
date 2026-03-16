After thorough analysis of the collateral factor boundary attack surface, I've examined:

1. **Collateral factor vs liquidation factor separation** - Properly implemented with admin validation (`CF < LF`, `LF*(1+LI) < 1`)
2. **Boundary conditions in solvency checks** - Correct: `>=` for solvency (inclusive), `>` for liquidation (exclusive), creating proper buffer zone
3. **Interest accrual asymmetry** - During borrow, only debt interest refreshed (not collateral) → conservative direction (undervalues collateral)
4. **Rounding in seize calculations** - `floor()` for seized ctokens, `ceil()` for debt amounts → protocol-favorable
5. **Borrow weight interaction** - Properly applied symmetrically in both solvency and liquidation contexts
6. **EMA vs spot price usage** - Known issues #003/#009
7. **Multi-collateral/multi-debt weighted sums** - Additive and correctly computed
8. **Close factor bypass with borrow_weight amplification** - Uses unweighted values for bad debt check, weighted for trigger → correct design
9. **`update_asset_borrow` with `saturating_sub`** - Correctly tracks delta including interest
10. **Non-collateral deposit handling** - `can_be_collateral()` checks `liquidation_factor > 0`, properly skipped in valuation

All potential boundary issues I identified are either:
- Already in the known bugs list (#003, #009, #028, #048, #052, #057)
- By-design conservative behavior (not exploitable)
- Require admin action as precondition (disqualified by Sherlock criteria)

NO_NEW_FINDINGS: The collateral factor boundary logic is well-implemented with proper admin validations, conservative rounding, correct factor separation between borrow/liquidation contexts, and consistent interest accrual. All edge cases at these boundaries either favor the protocol or are already documented as known issues.
