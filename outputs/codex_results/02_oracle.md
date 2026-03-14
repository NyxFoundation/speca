**Findings (Oracle-Focused)**

1. **High: Liquidation seizure uses raw spot price while risk checks use EMA**
- Root cause:
  - Liquidation seize math uses `get_spot_price` directly at [market.move:1045](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:1045) and [market.move:1046](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:1046).
  - `get_spot_price` only checks staleness/zero at [user.move:34](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/x_oracle/sources/entry_points/user.move:34) and [user.move:61](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/x_oracle/sources/entry_points/user.move:61).
  - Liquidation eligibility paths use EMA (`get_price`) at [market.move:1117](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:1117) and [market.move:1156](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:1156).
- Attack path:
  - Wait for a position already liquidatable by EMA checks.
  - Trigger oracle refresh near a short-lived spot dislocation.
  - Execute liquidation: seize amount is computed from manipulated spot ratio, not EMA/spot-checked price.
- Impact:
  - Over-seizure or under-seizure of collateral relative to fundamental price.
  - Economic extraction from borrowers and potential bad-debt amplification depending on direction.

2. **Medium: `get_price_with_check` deviation formula is asymmetric**
- Root cause:
  - Deviation uses `spot_price_value` as denominator in both branches at [user.move:50](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/x_oracle/sources/entry_points/user.move:50)-[user.move:54](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/x_oracle/sources/entry_points/user.move:54).
- Attack path:
  - For `spot > ema`, allowed deviation is effectively looser than a symmetric check.
  - Borrow safety paths using this function ([market.move:1198](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:1198), [market.move:1284](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:1284)) can pass larger one-sided EMA/spot gaps than configured.
- Impact:
  - Deviation guard is directionally biased and can be bypassed in one direction, weakening intended oracle sanity protection.

3. **Medium (config-sensitive): Staleness policy can admit materially stale cached prices**
- Root cause:
  - Read-time staleness uses admin-set tolerance in [x_oracle.move:148](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/x_oracle/sources/internal/x_oracle.move:148)-[x_oracle.move:150](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/x_oracle/sources/internal/x_oracle.move:150), capped at 30 minutes ([x_oracle.move:30](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/x_oracle/sources/internal/x_oracle.move:30)); enforced at [user.move:66](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/x_oracle/sources/entry_points/user.move:66)-[user.move:67](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/x_oracle/sources/entry_points/user.move:67).
- Attack path:
  - If tolerance is raised for liveness, users can transact against old cached oracle state until tolerance expiry.
  - No mandatory in-flow refresh in protocol entrypoints.
- Impact:
  - During volatile moves: underpriced debt / overpriced collateral windows, delayed liquidation correctness, and risk mispricing.

4. **Low (Pyth adapter edge case): startup underflow DoS window**
- Root cause:
  - `now - PRICE_FEED_DELAY_SECONDS` at [pyth_adaptor.move:85](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/x_oracle/sources/internal/pyth_adaptor.move:85) can underflow when chain time `< 30s`.
- Attack path:
  - In early chain lifetime, refresh aborts regardless of feed freshness.
- Impact:
  - Temporary inability to refresh oracle prices.

---

**Direct answers to your 5 focus questions**
1. **Staleness checks sufficient?** Not fully. They are dual-layered, but read-time tolerance can be large and exploitable if configured high.
2. **EMA vs spot inconsistency across code paths?** Yes, significant inconsistency exists (especially liquidation seize path).
3. **Can EMA be manipulated?** No direct contract-level EMA-manipulation primitive found; risk is inherited from Pyth market-level manipulation plus refresh timing.
4. **Deviation check (`get_price_with_check`) symmetric?** No, it is asymmetric.
5. **Pyth adaptor edge cases?** Yes, confirmed startup underflow edge; additional hardening is advisable.