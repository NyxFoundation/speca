After thorough analysis of the oracle system, price feed mechanisms, and all code paths where prices are consumed, I've examined:

1. **Oracle architecture**: Pyth-based with spot + EMA, 30s Pyth staleness, configurable protocol-level tolerance, confidence checks
2. **Price usage in liquidation**: EMA for eligibility, spot for seize calculation, EMA for close factor
3. **Price usage in non-liquidation**: EMA with spot divergence tolerance check (`get_price_with_check`)
4. **Rate limiter**: Price-agnostic (raw token amounts), by design
5. **Interest accrual ordering**: All paths correctly accrue interest before price-dependent operations
6. **Oracle update mechanism**: No regression possible (Pyth prevents it), atomic spot+EMA updates
7. **Exchange rate**: Independent of oracle prices, only depends on cash/debt/supply
8. **ADL parameters**: Time-based degradation, no direct price interaction

The protocol's oracle design is sound:
- Pyth confidence checks prevent wide-spread prices from being accepted
- Staleness checks at both Pyth level (30s) and protocol level (configurable) prevent stale price exploitation
- EMA provides smoothing for safety checks while spot is used for liquidation seize (deliberate design)
- The EMA-spot divergence check blocks borrow/withdraw during high volatility but allows liquidations (correct)
- All price-consuming paths properly refresh interest first

The known bugs 003 (spot_ema_price_inconsistency), 009 (oracle_deviation_asymmetric), and 052 (non_collateral_withdraw_oracle) already cover the oracle-related vulnerabilities in this codebase.

NO_NEW_FINDINGS: Price feed front-running angle is exhausted — oracle has proper Pyth staleness/confidence checks, EMA smoothing for safety checks, consistent interest accrual ordering, and no exploitable EMA-spot divergence path beyond known bugs 003/009/052. Sui's lack of traditional mempool further limits front-running attack surface.
