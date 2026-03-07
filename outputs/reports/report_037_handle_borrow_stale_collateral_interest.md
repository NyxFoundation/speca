# `handle_borrow` Uses Stale Collateral Exchange Rates in Obligation Safety Check

## Summary

`handle_borrow` only refreshes borrow-side interest before the obligation safety check, not collateral-side interest. This causes the safety check to undervalue collateral positions using stale exchange rates, potentially denying legitimate borrows.

## Vulnerability Detail

In `market.move:406-407`, `handle_borrow` explicitly only refreshes borrow interest:

```move
// refresh only borrow, practically, obligation owner can borrow a bit more due to collateral interest
refresh_obligation_borrow_interest_with_new_borrow<MarketType>(name, &self.assets, &mut self.reserves, obligation, now);
```

The comment acknowledges this is intentional but notes the consequence: "obligation owner can borrow a bit more due to collateral interest."

The subsequent safety check at line 424-434 calls `is_obligation_safe`, which internally computes collateral value using `reserve.exchange_rate()`:

```move
let is_obligation_safe = is_obligation_safe(
    emode_group,
    &self.reserves,
    &self.ema_spot_tolerance,
    self.obligations.borrow(obligation_id),
    coin_decimals_registry,
    x_oracle,
    clock,
);
```

If the collateral asset's reserve has not had `accrue_interest` called recently (e.g., no other user has interacted with that asset), the exchange rate is stale and lower than it should be (since accumulated interest increases the numerator `cash + debt - cash_reserve`).

Compare with `handle_withdraw` (line 324-326), which correctly refreshes ALL interest before the safety check:

```move
let emode_group = self.emode_group_registry.borrow_emode_group_mut(obligation.emode_group());
refresh_obligation_assets_interest<MarketType>(&self.assets, emode_group, &mut self.reserves, obligation, now);
```

## Impact

The stale exchange rate causes `is_obligation_safe` to **undervalue collateral** during borrow operations:

1. **Denied legitimate borrows:** A borrower with sufficient collateral may be rejected because the stale exchange rate undervalues their collateral. The discrepancy grows with time since the collateral asset's last interest accrual and the interest rate.

2. **Inconsistent behavior:** Two identical positions may get different borrow outcomes depending on whether another user happened to interact with the collateral asset recently (triggering interest accrual).

3. **Compounding effect with multiple collateral assets:** If a user has multiple collateral types, all of them may have stale exchange rates, compounding the undervaluation.

For example, with a collateral asset at 10% APR that hasn't been accrued for 24 hours:
- Stale exchange rate: 1.0
- Fresh exchange rate: 1.0 + (0.10 / 365) ≈ 1.000274
- For $10M in collateral, this is a ~$2,740 undervaluation

## Code Snippet

- `market.move:406-407` — `handle_borrow` only calls `refresh_obligation_borrow_interest_with_new_borrow`
- `market.move:424-434` — Safety check uses stale collateral exchange rates
- `market.move:324-326` — `handle_withdraw` correctly calls `refresh_obligation_assets_interest` (all assets)

## Tool used

Manual Review + Automated Analysis

## Recommendation

Refresh all obligation asset interest in `handle_borrow` before the safety check, consistent with `handle_withdraw`:

```move
// Replace line 406-407:
// refresh only borrow, practically, obligation owner can borrow a bit more due to collateral interest
// refresh_obligation_borrow_interest_with_new_borrow<MarketType>(name, &self.assets, &mut self.reserves, obligation, now);

// With:
refresh_obligation_assets_interest<MarketType>(&self.assets, emode_group, &mut self.reserves, obligation, now);
```

This ensures the safety check uses fresh exchange rates for all collateral assets, providing consistent behavior across all market operations.
