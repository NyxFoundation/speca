# Dust Obligations Become Unliquidatable Due to Seize Amount Flooring to Zero

## Summary

When an obligation has a very small debt position, the `liquidate_calculate_seize_ctokens` function floors the seize amount to zero, causing `liquidate_ctokens` to revert on its `assert!(ctokens.value() > 0)` check. This makes dust obligations permanently unliquidatable, accumulating bad debt.

## Vulnerability Detail

In `market.move:1073`, the seize cTokens calculation floors the result:

```move
fun liquidate_calculate_seize_ctokens<DebtType, CollateralType>(
    exchange_rate: Decimal,
    liquidation_incentive: Decimal,
    actual_repay_amount: u64,
    ...
): u64 {
    // ... calculation ...
    let seize_ctokens = seize_collaterals.div(exchange_rate);
    // only take the technically possible amount
    seize_ctokens.floor()  // <-- floors to 0 for tiny amounts
}
```

When the debt is very small (e.g., a few wei of a high-decimal token), the computed `seize_ctokens` value can be less than 1.0 in the Decimal representation. The `floor()` call truncates this to 0.

Later in `liquidation_inner` at `market.move:776`, the zero seized cTokens are withdrawn from the obligation and passed to `liquidate_ctokens`:

```move
let ctoken_balance = obligation.withdraw_ctokens<MarketType, CollateralType>(seized_ctokens);
let refund_balance = collateral_reserve.liquidate_ctokens<MarketType, CollateralType>(
    ctoken_balance.into_coin(ctx),
    liquidation_params.liquidation_revenue_factor,
);
```

In `reserve.move:171`, `liquidate_ctokens` asserts:

```move
assert!(ctokens.value() > 0, error::reserve_zero_coin_not_allowed());
```

This means any liquidation attempt on a dust obligation will always revert. The obligation becomes permanently underwater and unliquidatable, creating protocol-level bad debt.

**Attack scenario:**
1. A borrower creates many small obligations near the minimum borrow amount
2. Over time, accrued interest pushes some slightly underwater
3. If the remaining debt after partial repayment becomes dust-sized, or if price movements make the seize calculation floor to 0
4. These positions can never be liquidated, accumulating bad debt

## Impact

- **Permanent bad debt accumulation**: Dust obligations that go underwater can never be liquidated
- **Protocol insolvency risk**: Over time, many small unliquidatable positions erode the protocol's solvency
- **Griefing vector**: An attacker can deliberately create many near-minimum positions that eventually become unliquidatable dust

Severity is Medium because it requires specific conditions (very small positions and particular price/exchange rate ratios) but has a permanent, irrecoverable impact on protocol solvency.

## Code Snippet

- [`market.move:1073`](contracts/protocol/sources/internal/market/market.move#L1073): `seize_ctokens.floor()` truncates to 0
- [`market.move:776`](contracts/protocol/sources/internal/market/market.move#L776): `obligation.withdraw_ctokens` with zero amount
- [`reserve.move:171`](contracts/protocol/sources/internal/market/reserve.move#L171): `assert!(ctokens.value() > 0)` blocks zero-ctoken liquidation

## Tool used

Manual Review + Automated Analysis

## Recommendation

Add a minimum seize check before calling `liquidate_ctokens`, and if the seize amount is zero, allow the protocol to socialize the bad debt or write off the dust position:

```move
if (seized_ctokens == 0) {
    // Write off dust debt - protocol absorbs the loss
    let _residual = obligation.unsafe_repay_debt_only<MarketType, DebtType>(0);
    // Remove the zero-value debt entry
    // Return empty collateral and full refund
    return (sui::coin::zero(ctx), available_repay_coin, 0)
};
```

Alternatively, use `ceil()` instead of `floor()` for the seize calculation to ensure at least 1 cToken is seized, accepting the slight rounding loss for the borrower.
