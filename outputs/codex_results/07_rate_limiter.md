**Confirmed Findings**

1. **High: Liquidation path bypasses rate limiter entirely**
- Root cause:
  - [`market.move:745`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:745) has explicit `// NOTE: disable rate limit`.
  - `liquidation_inner` executes debt repayment + collateral outflow without any `add_outflow` limiter call (only borrow/deposit/withdraw/repay paths do).
- Attack path:
  - Wait until borrow/withdraw limiter is saturated.
  - Use liquidation routes (`handle_liquidation`/ADL variants -> `liquidation_inner`) to move large collateral/debt flows despite limiter exhaustion.
- Impact:
  - Rate limiter can be bypassed for large forced-position changes during liquidation events, undermining throttling guarantees exactly when market stress is highest.

2. **Medium: Limiter is token-amount based, not value-based (USD)**
- Root cause:
  - Limiter state/threshold are raw `u64` token amounts in [`limiter.move:8`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/limiter.move:8), [`limiter.move:41`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/limiter.move:41), [`limiter.move:81`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/limiter.move:81), [`limiter.move:103`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/limiter.move:103).
  - Market passes raw `borrow_amount`, `deposit.value()`, `coin.value()` into limiter calls at [`market.move:298`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:298), [`market.move:349`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:349), [`market.move:402`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:402), [`market.move:483`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:483).
- Attack path:
  - Exploit mismatch between economic value and token units (price moves/decimal effects) so effective USD throttling is weaker or stronger than intended.
- Impact:
  - Risk controls drift from real market value exposure.

3. **Medium: Cross-segment reduction is broken (current-segment-only saturation)**
- Root cause:
  - `reduce_outflow` only touches current segment index, saturating that single bucket to zero at most: [`limiter.move:106`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/limiter.move:106)-[`limiter.move:118`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/limiter.move:118).
  - Historic saturated segments in the active cycle are untouched.
- Attack path:
  - Build outflow across prior segments, then do large inflow now (repay/deposit). Inflow cannot clear prior segments, so limiter remains exhausted.
- Impact:
  - Prolonged throttle lock / denial-of-service behavior for new borrow/withdraw despite significant opposite flow.

4. **Medium (Privileged): Admin e-mode update resets limiter usage state**
- Root cause:
  - `emode.update` reconstructs both limiters via `new_from_struct`, resetting segments/usage: [`emode.move:309`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/emode.move:309)-[`emode.move:310`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/emode.move:310).
  - Admin entry `update_asset_in_emode_group` calls `emode.update(params)`: [`entry_points/admin/emode.move:135`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/entry_points/admin/emode.move:135)-[`entry_points/admin/emode.move:150`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/entry_points/admin/emode.move:150).
- Attack path:
  - Privileged actor updates asset config (even with same limiter params) to wipe live limiter usage.
- Impact:
  - Instant bypass of cooldown/rate-throttle assumptions by privileged control plane.

**Not Confirmed (from your checklist #2)**
- **Flash loan + deposit atomic limiter reset** is **not directly confirmed** as a clean zero-capital bypass from this code alone.
- Deposit does call `reduce_outflow` ([`market.move:298`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:298)), but a same-tx round-trip with flash-loaned funds typically re-adds outflow on withdrawal or requires external capital/net position to close the flash loan.  
