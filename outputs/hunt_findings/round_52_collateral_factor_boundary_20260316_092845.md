After thoroughly analyzing the codebase focusing on the "collateral_factor_boundary" strategy, I've traced through all the key code paths:

**Solvency check** (`is_obligation_safe`, line 1214-1249): Uses `collateral_factor` weighting with `>=` boundary (equality is safe).

**Liquidation trigger** (`ensure_liquidate_borrow_allowed`, line 926-1013): Uses `liquidation_factor` weighting with `>` boundary (strictly greater required). Two paths:
- Default: `weighted_debts > collateral_weighted_value`  
- ADL override: `weighted_debts / total_collateral > liquidation_ltv`

**Key areas investigated:**

1. **CF vs LF boundary gap**: The protocol correctly maintains a buffer zone between `collateral_factor` (borrow limit) and `liquidation_factor` (liquidation threshold). No missing validation is exploitable without admin action.

2. **Bad debt close factor bypass** (line 985-992): Uses unweighted values (`1.01 * debts_total_value`). With high `borrow_weight`, weighted debt can exceed weighted collateral while unweighted collateral > unweighted debt — close factor still enforced. This is correct design; the bad debt check tests actual insolvency.

3. **Non-collateral asset handling**: `can_be_collateral()` checks `liquidation_factor > 0`. Assets with LF=0 are consistently skipped in both solvency and liquidation calculations. The unused `withdraw` solvency check on non-collateral is known bug 052.

4. **Price functions**: Solvency uses `get_price_with_check` (EMA + spot divergence check), liquidation trigger uses `get_price` (EMA only), seize uses `get_spot_price`. The EMA/spot inconsistency is known bug 003.

5. **Math precision**: `int_mul`/`int_div` truncate toward zero. `mint_ctokens` truncates in favor of pool, `burn_ctokens` truncates in favor of pool. `ceil()` used for debt amounts.  All rounding is conservative.

6. **Emode parameter validation**: No validation that `collateral_factor <= liquidation_factor` or that either `<= 1.0`, but all changes require admin functions (`update_collateral`/`update_borrow`).

7. **ADL division by zero**: If `collateral_total_value = 0` in the override path (line 966), division by zero would abort — but this state requires admin setting all LFs to 0 after positions exist.

All potential issues either map to already-known bugs (003, 028, 031, 048, 052, 062) or require admin action as a precondition (which fails Sherlock HIGH criteria).

NO_NEW_FINDINGS: Collateral factor boundary conditions are handled correctly in solvency checks, liquidation triggers, and seize calculations. All factor-related misconfigurations require admin action. Price/rounding edge cases at boundaries are already captured in known bugs.
