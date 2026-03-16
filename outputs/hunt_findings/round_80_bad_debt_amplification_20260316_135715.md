After thorough analysis of the bad debt amplification vectors in the protocol, I've examined:

1. **Liquidation inner flow** (market.move:691-793) — residual handling, seize calculation, cap logic
2. **Bad debt close factor bypass** (market.move:984-992) — when collateral ≤ 1.01× debt
3. **Emode borrow tracking** (emode.move:183-192) — `update_asset_borrow` with `saturating_sub`
4. **ADL activation vs deactivation** — global debt vs per-group tracking
5. **Reserve accounting** — `repay_amount` handling of excess, `accrue_interest` flow
6. **Exchange rate effects** — phantom debt from unreclaimable bad debt
7. **Interest model** — utilization rate bounds, tri-kink rate behavior under high utilization
8. **Rounding in liquidation** — `seize_ctokens.floor()`, `expected_repay_amount.ceil()`

Every potential finding I traced maps to an already-known bug:
- Exchange rate inflation from phantom bad debt → **#062** (bad_debt_not_socialized)
- ADL activation using global reserve debt instead of per-group debt → **#004** (adl_global_debt_check)
- Spot vs EMA price asymmetry in liquidation → **#003** (spot_ema_price_inconsistency)
- `repay_fee_rate` used as reserve_factor → **#057** (repay_fee_rate_misused)
- ADL LTV dropping to zero → **#035** (adl_ltv_degrades)

The protocol's liquidation and bad debt handling, while imperfect (no socialization), is internally consistent in its accounting. The `saturating_sub` in emode tracking prevents underflow. The cap logic correctly proportions repayment when collateral is insufficient. Exchange rates are preserved through liquidation due to symmetric ctoken burns. The interest model is bounded by `cash >= cash_reserve` invariant preventing utilization > 1.

NO_NEW_FINDINGS: All bad debt amplification vectors trace back to already-known bugs (#062 bad_debt_not_socialized, #004 adl_global_debt_check, #003 oracle inconsistency, #057 repay_fee_rate, #035 adl_ltv_degrades). Core liquidation accounting is correct.
