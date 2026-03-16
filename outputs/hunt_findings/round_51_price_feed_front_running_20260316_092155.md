I've done a thorough analysis of the price feed mechanism across the entire protocol. Let me summarize what I examined:

**Oracle system:**
- `refresh_usd_price` is permissionless — stores both EMA and spot from Pyth with separate timestamps
- `check_price` validates staleness: `clock.timestamp_ms() - last_updated * 1000 <= price_delay_tolerance_ms`
- Pyth adaptor enforces 30-second staleness and confidence tolerance at refresh time

**Price usage across operations:**
- **Borrow/Withdraw (non-liquidation):** Uses `get_price_with_check()` — EMA price with EMA-spot deviation validation
- **Liquidation eligibility:** Uses `get_price()` — EMA price only, no deviation check  
- **Liquidation seize calculation:** Uses `get_spot_price()` — spot price for both debt and collateral
- **Close factor enforcement:** Uses `get_price()` — EMA for debt value calculation

**Known bugs that cover this territory:**
- `#003` — spot/EMA inconsistency between liquidation eligibility and seize
- `#009` — asymmetric deviation check (divides by spot in both branches)
- `#031` — circuit breaker blocking liquidation
- `#052` — non-collateral withdraw oracle check

**Angles explored without finding new bugs:**
1. Selective price refresh (stale one asset, fresh another) — staleness check per-asset at read time prevents exploitation
2. Pyth EMA vs spot timestamp divergence — both validated independently, both must be within 30s
3. Flash loan + price interaction — only used for referral tracking (non-critical)
4. Rate limiter uses token amounts not USD — design decision, not directly exploitable for fund loss
5. Emode borrow tracking with interest — `update_asset_borrow` correctly tracks delta
6. Float precision (18-decimal u256) — no overflow/precision issues in seize calculation
7. Liquidation requires `PackageCallerCap` — permissioned, limits attack surface
8. Close factor bypass at 101% threshold uses EMA — consistent with rest of liquidation

NO_NEW_FINDINGS: Price feed front-running is structurally difficult on Sui (no mempool-based ordering). The oracle's dual-layer staleness checks (Pyth 30s + configurable tolerance) prevent stale price exploitation. All major EMA/spot inconsistency vectors are covered by known bugs #003 and #009. The remaining price-adjacent code paths (limiter, flash loan referral, interest accrual) don't create exploitable fund-loss scenarios.
