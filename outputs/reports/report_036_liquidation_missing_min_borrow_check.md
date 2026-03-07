# Liquidation Skips min_borrow_amount Check, Creating Unclearable Dust Positions

## Summary

The `liquidation_inner` function does not enforce the `min_borrow_amount` invariant after partial debt repayment, allowing liquidators to leave borrowers with dust debt positions below the minimum threshold. These positions become effectively unclearable and accumulate bad debt.

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

## Impact

1. A liquidator can partially liquidate an obligation, leaving debt below `min_borrow_amount` (e.g., `min_borrow_amount = 100 USDC`, remaining debt = 5 USDC)
2. The borrower cannot partially repay this position (the `enforce_post_borrow_repay_invariant` in `handle_repay` would reject it unless the full remaining amount is repaid)
3. If the position is underwater, no one has economic incentive to fully repay it
4. The dust position continues accruing interest, inflating the reserve's `debt` tracker without corresponding repayment
5. Over many liquidations across many users, this systematically accumulates unclearable bad debt

## Code Snippet

- `contracts/protocol/sources/internal/market/market.move:773-774` — missing invariant check after `unsafe_repay_debt_only` in `liquidation_inner`
- `contracts/protocol/sources/internal/market/market.move:413` — invariant check present in `handle_borrow`
- `contracts/protocol/sources/internal/market/market.move:470` — invariant check present in `handle_repay`
- `contracts/protocol/sources/internal/market/obligation.move:154-166` — `enforce_post_borrow_repay_invariant` definition

## Tool used

Manual Review + Automated Analysis

## Recommendation

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
