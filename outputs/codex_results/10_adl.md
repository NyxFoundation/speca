**Confirmed Vulnerabilities**

1. **Debt ADL activation uses global reserve debt, not eMode-group debt (high)**
- Root cause:
  - Debt ADL config is keyed by `emode_group_id` via `get_borrow_deleverage(debt_type, emode_group_id)` in [`market.move`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:575).
  - But breach check uses market-wide reserve debt:
    - `let total_debt = (*self.reserves.load_by_type(debt_type).debt()).floor();`
    - `debt_params.ensure_limit_breached(total_debt);`
    - at [`market.move`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:580).
  - Group-specific debt accounting exists and is used elsewhere (`emode_group.borrow_amount`) in [`emode.move`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/emode.move:194).
- Attack path:
  1. Enable debt ADL for `(DebtType, emode_group_id=A)` with target `T`.
  2. Global `DebtType` debt exceeds `T` because of other groups (e.g., group B), while group A may already be <= `T`.
  3. ADL-liquidation keeper calls `liquidate_adl_borrow` on a group-A obligation.
  4. Check passes due to global debt, enabling forced liquidation/seizure on group A.
- Impact:
  - Cross-group contamination: borrowers in a non-breaching group can be forcibly ADL-liquidated due to debt from other groups.
  - Unintended collateral seizure and user loss in unaffected group.

2. **Activation vs stop condition scope mismatch for debt ADL (high)**
- Root cause:
  - Activation gate in execution path uses global reserve debt (`reserves.debt`) at [`market.move:580`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:580).
  - Stop logic uses eMode-group debt (`emode_group.borrow_amount`) in `try_stop_borrow_deleverage` at [`market.move:686`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:686), then registry stop check at [`adl.move:144`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/adl.move:144).
- Attack path:
  1. Same setup as above; activation repeatedly allowed by global debt.
  2. After one/few liquidations, group-A debt drops to target and ADL auto-stops for group A.
  3. Global debt can still remain above target (from other groups), but group-A ADL is deactivated.
- Impact:
  - ADL lifecycle is inconsistent: wrong-trigger + premature stop relative to activation metric.
  - Produces both unfair liquidations and unreliable deleveraging behavior versus intended control surface.

**Not confirmed as vulnerability**

- **“Debt ADL incorrectly seizes collateral because `liquidation_inner` always calls `withdraw_ctokens`”**: not confirmed.
  - Both ADL entrypoints are explicitly liquidation flows and transfer seized collateral to caller (`liquidate_adl_borrow` / `liquidate_adl_deposit`) in [`liquidate.move`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/entry_points/lending/liquidate.move:229).
  - `liquidation_inner` is shared liquidation logic and collateral seizure is consistent with that design at [`market.move:776`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:776).