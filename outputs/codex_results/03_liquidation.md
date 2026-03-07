**Confirmed Vulnerabilities**

1. **Oracle source mismatch in liquidation (EMA for eligibility, spot for seize) enables over-seizure**
- Root cause:
  - Liquidation eligibility uses `get_price` (EMA path) in [`market.move:944`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:944), [`market.move:953`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:953), [`market.move:1115`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:1115), [`market.move:1155`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:1155).
  - Seizure amount uses `get_spot_price` in [`market.move:1045`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:1045)-[`1046`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:1046).
  - Liquidation path does not apply `ema_spot_tolerance` checks used by borrow/withdraw.
- Attack path:
  - Pick an obligation already eligible by EMA-based check.
  - Manipulate spot ratio (debt spot up and/or collateral spot down) at liquidation execution.
  - Repay bounded debt, but seize disproportionately high collateral via spot-based formula.
- Impact:
  - Excess collateral seizure beyond intended economics, faster borrower loss, and potential reserve stress/bad debt amplification.

2. **ADL borrow uses wrong scope for breach check (global reserve debt vs per-emode debt)**
- Root cause:
  - ADL borrow params are loaded per `(debt_type, emode_group_id)` in [`market.move:574`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:574)-[`575`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:575),
  - but breach check uses **global** reserve debt in [`market.move:580`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:580)-[`582`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:582).
  - Stop logic later uses emode-group borrow amount in [`market.move:685`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:685)-[`688`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:688), showing inconsistency.
- Attack path:
  - If total debt for a coin is high due to other groups, ADL borrow liquidation can be executed on a target emode group whose own debt is below its configured threshold.
- Impact:
  - Incorrect ADL borrow liquidations and unjustified collateral seizure for obligations in unaffected emode groups.

3. **Liquidation bypasses outflow rate limiter**
- Root cause:
  - Normal withdraw enforces deposit outflow limiter in [`market.move:347`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:347)-[`352`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:352).
  - Liquidation path explicitly notes disabled limiter and performs ctoken withdrawal + underlying withdrawal without limiter accounting in [`market.move:745`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:745), [`market.move:776`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:776), [`market.move:778`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:778), [`reserve.move:166`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:166)-[`181`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:181).
- Attack path:
  - During stressed conditions, whitelisted liquidators can extract collateral outflows unconstrained by deposit limiter protections.
- Impact:
  - Rate-limit protections are ineffective for the largest stress-flow path (liquidations), increasing liquidity-run risk.

---

**Checks you asked about (explicit answers)**

1. Different price sources for eligibility vs seizure: **Yes (confirmed vulnerability #1).**  
2. Close factor misapplication / excessive liquidation: **No standalone close-factor bug confirmed**; close-factor is enforced with explicit designed bypasses (near bad debt / small debt).  
3. Self-liquidation profitable: **Conditionally yes** if combined with oracle mismatch (vuln #1). No standalone guaranteed-profit self-liquidation bug found in the reviewed code alone.  
4. ADL borrow vs ADL collateral logic: **Yes, confirmed ADL borrow scope bug** (vulnerability #2).  
5. Liquidation bypasses rate limiters: **Yes (confirmed vulnerability #3).**