# Liquidation Skips min_borrow_amount Check, Creating Economically Unclearable Dust Positions

## Summary

The `liquidation_inner` function does not enforce the `min_borrow_amount` invariant after partial debt repayment, allowing liquidators to leave borrowers with dust debt positions below the minimum threshold. These positions become economically unclearable (full repay is technically possible but not incentivized) and accumulate bad debt.

## Vulnerability Detail

In `market.move`, both `handle_borrow` (line 413) and `handle_repay` (line 470) call `enforce_post_borrow_repay_invariant` to ensure remaining debt stays above `min_borrow_amount`:

```move
// handle_borrow - line 413
obligation.enforce_post_borrow_repay_invariant<MarketType, CoinType>(min_borrow_amount);

// handle_repay - line 470
obligation.enforce_post_borrow_repay_invariant<MarketType, CoinType>(min_borrow_amount);
```

However, `liquidation_inner` (line 774) repays debt without this check:

```move
// market.move:773-774
// at this stage, even if there is residual, it should be a very small amount, let the protocol consume the residual
let _residual = obligation.unsafe_repay_debt_only<MarketType, DebtType>(available_repay_coin.value());
// NOTE: NO enforce_post_borrow_repay_invariant call here
```

The `enforce_post_borrow_repay_invariant` function (obligation.move:154-166) asserts:

```move
public(package) fun enforce_post_borrow_repay_invariant<MarketType, CoinType>(
    self: &Obligation<MarketType>,
    min_borrow_amount: u64
) {
    let coin_type = type_name::with_defining_ids<CoinType>();
    if (!self.has_debt<MarketType>(coin_type)){ return };
    let current_debt = self.debt<MarketType>(coin_type).unsafe_debt_amount();
    assert!(current_debt.ge_u64(min_borrow_amount), error::obligation_borrow_below_min());
}
```

Note: This is distinct from report 028 (dust obligations unliquidatable due to seize flooring to zero). Report 028 covers the case where `seize_ctokens.floor() == 0`, making the position unliquidatable. This report covers the broader case where a partial liquidation reduces debt below `min_borrow_amount`, creating a position that is stuck — it cannot be partially repaid (the invariant check in `handle_repay` blocks it) and may not be economically worth fully repaying.

Additionally, report 059 (Liquidation Residual Consumed as Revenue) shows that ceiling rounding during liquidation causes the liquidator to overpay by 1-2 units per event. This compounds with the dust creation: the liquidator is overcharged on the very liquidation that creates the unclearable dust position.

## Internal Pre-conditions

1. Obligation must have debt that becomes partially liquidatable.
2. Liquidation must reduce remaining debt below min_borrow_amount.

## External Pre-conditions

1. Price movement or interest accrual must push the obligation below its liquidation threshold.

## Attack Path

1. Borrower has debt of 150 USDC with min_borrow_amount = 100 USDC.
2. Position becomes liquidatable due to price drop.
3. Liquidator partially liquidates, repaying 100 USDC of debt.
4. Remaining debt = 50 USDC, below min_borrow_amount.
5. No enforce_post_borrow_repay_invariant check in liquidation_inner.
6. Borrower cannot partially repay the 50 USDC dust (handle_repay blocks it).
7. Full repay is possible but economically irrational for underwater dust.
8. Dust position accumulates bad debt over time.

## Impact

1. A liquidator can partially liquidate an obligation, leaving debt below `min_borrow_amount` (e.g., `min_borrow_amount = 100 USDC`, remaining debt = 5 USDC)
2. The borrower cannot partially repay this position (the `enforce_post_borrow_repay_invariant` in `handle_repay` would reject it unless the full remaining amount is repaid). Note: full repay IS technically possible, but economically irrational for underwater dust positions.
3. If the position is underwater, no one has economic incentive to fully repay it
4. The dust position continues accruing interest, inflating the reserve's `debt` tracker without corresponding repayment
5. Over many liquidations across many users, this systematically accumulates economically unclearable bad debt

## Code Snippet

- `contracts/protocol/sources/internal/market/market.move:773-774` — missing invariant check after `unsafe_repay_debt_only` in `liquidation_inner`
- `contracts/protocol/sources/internal/market/market.move:413` — invariant check present in `handle_borrow`
- `contracts/protocol/sources/internal/market/market.move:470` — invariant check present in `handle_repay`
- `contracts/protocol/sources/internal/market/obligation.move:154-166` — `enforce_post_borrow_repay_invariant` definition

## Tool used

Manual Review + Automated Analysis

## Mitigation

Add a `min_borrow_amount` check after liquidation debt repayment, or force full repayment when remaining debt would fall below the minimum:

```move
// In liquidation_inner, after line 774:
let _residual = obligation.unsafe_repay_debt_only<MarketType, DebtType>(available_repay_coin.value());

// If remaining debt is below min_borrow_amount, force full clearance
if (obligation.has_debt(debt_name)) {
    let remaining = obligation.debt(debt_name).unsafe_debt_amount();
    let min_borrow = assets.load_by_type(debt_name).asset_config().min_borrow_amount();
    if (remaining.lt_u64(min_borrow)) {
        obligation.unsafe_repay_debt_only<MarketType, DebtType>(remaining.ceil());
    };
};
```
