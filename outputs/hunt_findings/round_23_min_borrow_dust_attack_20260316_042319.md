After thorough analysis of the min_borrow_dust_attack vector, here's my assessment:

## Analysis Summary

I traced all code paths that could create or interact with dust positions:

**Paths examined:**

1. **`enforce_post_borrow_repay_invariant`** (obligation.move:154-166) - Correctly enforced after both `handle_borrow` (market.move:413) and `handle_repay` (market.move:470). Uses `ge_u64` comparison which is correct for Decimal vs u64.

2. **Liquidation path** (`liquidation_inner`, market.move:691-793) - Calls `unsafe_repay_debt_only` at line 774 without any min_borrow check → **already known as `036:liquidation_min_borrow`**

3. **ADL liquidation** (`handle_debt_auto_deleverage`, `handle_collateral_auto_deleverage`) - Both delegate to `liquidation_inner`, same gap → same known bug

4. **`repay_on_behalf`** - Anyone can call with any obligation_id, but `enforce_post_borrow_repay_invariant` is checked, preventing dust creation via partial repay

5. **Interest accrual rounding** - Uses 18-decimal fixed-point (`WAD = 10^18`). For USDC (6 decimals), 1 unit = 10^12 in WAD representation. Rounding errors are negligible (~10^-18 token units per operation).

6. **Emode borrow tracking** (`update_asset_borrow` in emode.move:183-192) - Uses `saturating_sub` which could mask accounting errors, but the delta calculation (new_value - old_value) is consistent across borrow/repay/liquidation paths.

7. **Reserve vs obligation debt consistency** - Both are independently tracked but consistently updated. The refund logic in liquidation uses `ceil()` matching `unsafe_repay_debt_only`'s `ceil()`, preventing discrepancies.

8. **Admin min_borrow change** - Could lock existing positions, but requires admin action (excluded by Sherlock criteria).

**All dust creation vectors are covered by known bugs 028 and 036. No novel min_borrow bypass exists.**

NO_NEW_FINDINGS: All min_borrow dust attack vectors are covered by known bugs 028 (dust_obligation_unliquidatable) and 036 (liquidation_min_borrow). The enforce_post_borrow_repay_invariant is correctly applied on all user-facing borrow/repay paths. The only gap is liquidation (already reported). Interest accrual rounding at 18-decimal precision is negligible. The repay_on_behalf function properly enforces min_borrow preventing third-party dust creation.
