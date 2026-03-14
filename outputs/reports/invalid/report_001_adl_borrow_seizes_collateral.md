# ADL Borrow operator will cause collateral loss to obligation holders

## Summary

`handle_debt_auto_deleverage` unconditionally routes through `liquidation_inner`, which seizes collateral from the obligation, causing obligation holders to lose collateral proportional to the repay amount plus liquidation incentive when ADL Borrow deleveraging is triggered, despite the intended behavior being debt-only reduction.

## Root Cause

In [`market.move:597-610`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L597-L610), `handle_debt_auto_deleverage` calls `liquidation_inner` without any differentiation from normal liquidation. Inside `liquidation_inner` at [`market.move:776`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L776), `obligation.withdraw_ctokens(seized_ctokens)` is called unconditionally — there is no branch to skip collateral seizure for the ADL Borrow path.

The ADL Borrow mechanism is designed to reduce system-wide borrow exposure by repaying an obligation's debt without seizing collateral. However, because both `handle_liquidation` (normal liquidation) and `handle_debt_auto_deleverage` (ADL Borrow) share the same `liquidation_inner` function, the ADL Borrow path incorrectly seizes collateral identical to a normal liquidation.

## Internal Pre-conditions

1. System-wide total borrow for a debt type in an emode group needs to breach the ADL borrow deleverage limit configured in the `AutoDeleverageRegistry`.
2. The ADL borrow deleverage timelock for the debt type needs to be activated (non-zero `activation_time`).
3. The target obligation needs to have both debt of `DebtType` and collateral of `CollateralType`.

## External Pre-conditions

None. This is a code logic error, not dependent on external state.

## Attack Path

1. Market conditions cause the total borrow of a specific debt type to breach the ADL borrow limit (`debt_params.ensure_limit_breached(total_debt)` passes at `market.move:582`).
2. An ADL operator (holding `PackageCallerCap` with ADL permission) calls `liquidate_adl_borrow<MarketType, DebtType, CollateralType>()` at `liquidate.move:210` targeting an obligation.
3. `handle_debt_auto_deleverage` at `market.move:546` constructs `LiquidationParams` and calls `liquidation_inner` at `market.move:597`.
4. Inside `liquidation_inner`, `liquidate_calculate_seize_ctokens` at `market.move:750` computes the collateral to seize based on `repay_amount * (1 + liquidation_incentive) * price_ratio / exchange_rate`.
5. `obligation.withdraw_ctokens(seized_ctokens)` at `market.move:776` removes the cTokens from the obligation.
6. The seized collateral is transferred to the ADL operator (liquidator) at `liquidate.move:254`.
7. The obligation holder's debt is reduced but they also lose collateral, violating the ADL Borrow invariant.

## Impact

The obligation holder suffers a loss of collateral proportional to the repay amount multiplied by `(1 + liquidation_incentive)`. For example, if 1000 USDC of debt is repaid with a 10% liquidation incentive, the obligation holder loses ~1100 USDC worth of collateral cTokens despite the ADL Borrow specification requiring collateral to remain unchanged.

This effectively converts ADL Borrow (a protocol safety mechanism that should only reduce debt) into a full liquidation that penalizes obligation holders who have done nothing wrong — their positions may be fully healthy, but they are targeted simply because the system-wide borrow limit was breached.

## PoC

The vulnerability can be confirmed by code inspection:

1. `handle_debt_auto_deleverage` (`market.move:546-611`) calls `liquidation_inner` at line 597.
2. `liquidation_inner` (`market.move:691-793`) unconditionally executes:
   - `liquidate_calculate_seize_ctokens` at line 750 — calculates collateral to seize
   - `obligation.withdraw_ctokens(seized_ctokens)` at line 776 — withdraws collateral from obligation
   - Returns seized collateral as `Coin<CollateralType>` at line 792
3. There is no `LiquidationType` parameter or conditional branch in `liquidation_inner` to skip collateral seizure for ADL Borrow.
4. Compare with the entry point `liquidate_adl_borrow` (`liquidate.move:210-256`): it receives the returned collateral and transfers it to the liquidator at line 254.

## Mitigation

Modify `handle_debt_auto_deleverage` to not seize collateral. Options include:

1. **Create a separate `adl_borrow_inner` function** that repays debt without computing or withdrawing collateral cTokens, returning zero collateral.
2. **Add a `LiquidationType` parameter to `liquidation_inner`** and skip the collateral seizure block (lines 750-781) when `liquidation_type == ADLBorrow`.
3. **Set `liquidation_incentive` to zero and skip cToken withdrawal** for the ADL Borrow path, ensuring the function only reduces debt.

The simplest fix is option 1 — a dedicated function that calls `obligation.unsafe_repay_debt_only` without calling `obligation.withdraw_ctokens`.
