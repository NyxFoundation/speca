After thorough analysis of all liquidation-related code paths, I've traced the complete liquidation flow including:

1. **`liquidate_calculate_seize_ctokens`** (market.move:1031-1074) — seize formula, price usage, rounding
2. **`ensure_liquidate_borrow_allowed`** (market.move:927-1013) — close factor, bad debt bypass
3. **`liquidation_inner`** (market.move:691-793) — ctoken cap, debt repayment, reserve accounting
4. **`liquidate_ctokens`** (reserve.move:166-182) — revenue factor, underlying withdrawal
5. **ADL incentive scaling** (adl.move:201-213) — time-based growth, safety cap via `.min()`
6. **`float.move` arithmetic** — overflow bounds, precision in chain of mul/div operations

Key findings from the analysis:

- **Seize formula math is correct**: `repay * (1 + incentive) * price_debt / price_collateral / exchange_rate` with proper decimal normalization
- **Rounding consistently favors protocol/borrower**: `floor()` on seized ctokens, `ceil()` on repay when capped by ctokens
- **ADL incentive is safely capped**: `.min(max_liquidation_incentive)` prevents unbounded growth
- **Decimal overflow in `mul`**: Only reachable with unrealistic values (>$18B single liquidation for 9-decimal BTC at $100k). Sui tokens are 9 decimals, keeping intermediates within VALUE_MAX_256 bounds
- **Exchange rate consistency**: Same exchange rate used for seize calculation and ctoken redemption within a single liquidation tx
- **EMA vs spot price discrepancy**: Liquidation eligibility uses EMA; seizure uses spot — this is known issue #003
- **Close factor bypass + bad debt**: Known as #048 and #062
- **`liquidation_revenue_factor` accounting**: Correctly splits seized collateral between liquidator and protocol reserve

NO_NEW_FINDINGS: The liquidation incentive calculations are mathematically sound with conservative rounding. Decimal overflow only occurs at unrealistic values far beyond practical limits for Sui's 9-decimal tokens. All identified edge cases (spot/EMA divergence, close factor bypass, bad debt creation) are already cataloged in the known bugs list (#003, #048, #062).
