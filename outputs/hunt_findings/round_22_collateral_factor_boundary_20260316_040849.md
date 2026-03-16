After thorough analysis of the collateral factor boundary code paths across the entire protocol, I've systematically examined:

1. **Collateral factor validation** (`admin/emode.move:87-96`): CF < LF, LF-CF < LI, LF*(1+LI) < 1 — all properly enforced
2. **Solvency checks** (`market.move:1214-1249` vs `1086-1126`): CF for borrow/withdraw (ge boundary = safe), LF for liquidation (gt boundary = liquidatable) — correctly implemented
3. **Seize calculation** (`market.move:1031-1074`): `floor()` rounding favors protocol, exchange rate consistent between calculation and redemption
4. **Close factor & bad debt bypass** (`market.move:984-1012`): per-debt-type check, 101% threshold — already known (#048)
5. **Interest accrual timing**: Borrow path only accrues debt interest (conservative for collateral valuation), liquidation accrues all — correct behavior
6. **Oracle price usage**: Non-liquidation uses `get_price_with_check` (EMA + divergence), liquidation uses `get_price` (EMA only), seize uses `get_spot_price` — already known (#003)
7. **Exchange rate preservation** through liquidation: `liquidate_ctokens` properly maintains rate by keeping protocol cut in `cash_reserve` while burning ctokens proportionally
8. **Rate limiters**: Disabled during liquidation (line 745 comment) — correct design
9. **Emode borrow tracking** (`update_asset_borrow` with `saturating_sub`): consistent accounting in borrow/repay/liquidation flows
10. **Admin update path**: `update_asset_in_emode_group` requires params from `create_emode_params` which enforces all invariants
11. **Multi-collateral liquidation**: liquidator chooses collateral, incentive from chosen collateral, close factor limits repay — standard Compound design

Every potential boundary issue I traced maps to either correct-by-design behavior or an already-known bug (#003, #009, #025, #028, #032, #048, #052, #057).

NO_NEW_FINDINGS: All collateral factor boundary conditions are properly validated and enforced. The gap between CF (borrow safety) and LF (liquidation trigger) works correctly. Rounding consistently favors the protocol. Exchange rates are consistent through liquidation. All edge cases I traced either are handled correctly or map to already-known issues.
