After thorough analysis of the collateral factor boundary area, I've examined all the key code paths:

1. **Solvency check** (`is_obligation_safe`): Uses `collateral_factor` weighting - boundary at equality is SAFE
2. **Liquidation trigger** (`ensure_liquidate_borrow_allowed`): Uses `liquidation_factor` weighting - strictly greater than required
3. **Admin validation** (`create_emode_params`): Properly enforces `CF < LF`, `LF * (1 + LI) < 1`, `BW >= 1`
4. **Seize calculation**: Uses `floor()` conservatively, handles insufficient ctokens
5. **Interest accrual**: Only borrow interest refreshed before borrow (conservative - underestimates collateral), all interest refreshed before withdrawal/liquidation
6. **Exchange rate**: Standard `(cash + borrows - reserves) / totalSupply`, properly initialized to 1.0
7. **ADL division-by-zero**: When `collateral_total_value = 0`, the ADL LTV calculation reverts, but this only affects zero-collateral obligations (bad debt) that rational liquidators wouldn't target - low severity
8. **Emode group borrow tracking**: `saturating_sub` defensively handles underflow, interest deltas correctly propagated
9. **Price functions**: Solvency uses EMA-checked price, liquidation trigger uses EMA, seize uses spot - already known bug #003
10. **ctoken cleanup**: Properly removes entries when balance reaches zero

All identified potential issues are either by-design, already known bugs, or below HIGH severity threshold.

NO_NEW_FINDINGS: The collateral_factor_boundary area is well-designed with proper separation of CF/LF, admin-validated invariants (CF < LF, LF*(1+LI) < 1, BW >= 1), consistent 18-decimal math, and conservative rounding. No exploitable boundary condition exists that meets Sherlock HIGH criteria without requiring admin action.
