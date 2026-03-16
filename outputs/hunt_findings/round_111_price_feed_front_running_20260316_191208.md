I've done a thorough analysis of the price feed front-running angle. Let me summarize my findings.

## Analysis Summary

I examined the complete price oracle flow:

1. **Oracle architecture** (x_oracle): Pyth-based, stores both spot and EMA prices, 30s Pyth staleness + 5s protocol staleness, per-asset confidence tolerance
2. **Solvency checks** (market.move): Uses `get_price_with_check()` → EMA with deviation check (default 10% tolerance)
3. **Liquidation eligibility**: Uses `get_price()` → EMA without deviation check
4. **Liquidation seize**: Uses `get_spot_price()` → spot price
5. **Close factor enforcement**: Uses `get_price()` → EMA for USD value threshold

**All price-related attack vectors I identified map to known bugs:**

- EMA/spot inconsistency between liquidation eligibility and seize calculation → **#003**
- Deviation formula `|ema-spot|/spot` creates asymmetric tolerance → **#009**
- Close factor bypass via per-debt EMA-based USD threshold → **#048**
- Non-collateral withdraw still requires oracle check → **#052**

**Other angles explored with no new findings:**
- Selective price refresh across assets: mitigated by 5s staleness window
- Flash loan interaction with exchange rate: `cash` field correctly isolated
- EMode borrow tracking staleness: soft limit, not solvency constraint, bounded by interest rates
- Rounding in seize calculation: conservative (floor), trivial magnitude
- ADL price interactions: consistent use of EMA, proper interest accrual before checks
- Pyth confidence overflow: bounded by guardian-signed VAAs
- Price=0 edge case: guarded by `assert!(price_value > 0)`
- Sui doesn't have a public mempool, making traditional front-running structurally difficult

NO_NEW_FINDINGS: The price feed front-running angle is well-covered by known bugs #003, #009, #048, and #052. Sui's lack of mempool-based MEV, the 5-second staleness tolerance, and consistent EMA usage within each price consumption path prevent new HIGH-severity exploits in this area.
