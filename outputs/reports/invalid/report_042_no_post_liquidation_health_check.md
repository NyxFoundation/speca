# No Post-Liquidation Health Check Allows Strategic Debt Selection to Worsen Obligation State

## Summary

The `liquidation_inner` function performs a pre-liquidation safety check but no post-liquidation health check, allowing liquidators to strategically choose which debt type to repay in order to maximize their incentive while leaving the obligation in a worse state than necessary.

## Vulnerability Detail

In `liquidation_inner` (market.move:691-793), the only safety check is the pre-liquidation `ensure_liquidate_borrow_allowed` call at line 722:

```move
// market.move:722-731
ensure_liquidate_borrow_allowed<MarketType, DebtType>(
    liquidation_params,
    obligation,
    emode_group,
    reserves,
    coin_decimals_registry,
    available_repay_coin.value(),
    x_oracle,
    clock,
);
```

After the liquidation executes (debt repaid at line 774, collateral seized at line 776-778), no post-liquidation check verifies the resulting health factor. Compare this to `handle_borrow` (market.move:434) and `handle_withdraw` (market.move:342) which both assert:

```move
assert!(is_obligation_safe, error::obligation_not_safe_after_operation());
```

When the close factor is bypassed near the bad debt threshold (market.move:985-992):

```move
let bad_debt_close_factor_bypass_threshold = float::from_quotient(101, 100);
let bad_debt_threshold = bad_debt_close_factor_bypass_threshold.mul(debts_total_value);
if (collateral_total_value.le(bad_debt_threshold)) {
    return  // close_factor effectively equals 1
};
```

A liquidator can repay 100% of a single debt type and seize the corresponding collateral value plus incentive. When an obligation has multiple debt types, the liquidator can cherry-pick the most profitable debt to repay (e.g., one with the most collateral incentive), leaving the remaining debts with less proportional collateral backing than before the liquidation.

Attack scenario:
1. Obligation has debt A ($500) and debt B ($500), collateral X ($1020, ~1.02x coverage → near bad debt)
2. Close factor is bypassed since within 101% threshold
3. Liquidator repays all of debt A ($500), seizes $500 * (1 + incentive) worth of collateral X
4. After liquidation: debt B ($500) remains with much less collateral backing
5. Debt B becomes bad debt more quickly than if the liquidation had been proportional

## Impact

Liquidators can maximize their own profit by selectively targeting the most favorable debt-collateral pairs in multi-debt obligations. Without a post-liquidation health check, the remaining positions can be left in a worse state than a proportional liquidation would produce. This accelerates bad debt accumulation in the protocol.

## Code Snippet

- market.move:691-793 (`liquidation_inner` — no post-liquidation check)
- market.move:434 (`handle_borrow` post-check for comparison)
- market.move:342 (`handle_withdraw` post-check for comparison)
- market.move:985-992 (close factor bypass near bad debt threshold)

## Tool used

Manual Review + Automated Analysis

## Recommendation

Add a post-liquidation check to ensure the liquidation improved the obligation's health ratio, or enforce proportional liquidation across debt types when the close factor is bypassed:

```move
// After line 787 in liquidation_inner:
// Verify the obligation's health improved (or debt fully cleared)
if (obligation.has_debt(debt_name)) {
    let (is_safe, _) = obligation_safety_check(...);
    // At minimum, ensure the health ratio improved compared to pre-liquidation
}
```

Alternatively, require liquidators to repay all debt types proportionally when close factor bypass is active.
