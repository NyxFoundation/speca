# Stale emode borrow tracking will block legitimate borrowers from borrowing

## Summary

`update_asset_borrow` in `handle_borrow` captures the obligation's old debt amount before interest accrual, causing the emode group's total borrow counter to systematically undercount accrued interest on inactive obligations, which can lead to premature borrow limit exhaustion when obligations interact after long idle periods.

## Root Cause

In [`market.move:404`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L404), the old borrow amount is read **before** interest accrual:

```move
let obligation_old_total_borrow_amount = if (!obligation.has_debt(name)) { float::zero() }
    else { obligation.debt(name).unsafe_debt_amount() };
```

Then at line 407, interest is accrued via `refresh_obligation_borrow_interest_with_new_borrow`. At line 421:

```move
let emode_group_total_borrow = emode_group.update_asset_borrow(
    name, obligation_old_total_borrow_amount, obligation_new_total_borrow_amount
);
```

The `update_asset_borrow` in [`emode.move:183-191`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/emode.move#L183-L191) computes:

```move
let new_borrow = new_value.add(*current_borrow).saturating_sub(old_value);
```

Since `old_value` is pre-interest and `new_value` is post-interest + post-borrow, the delta `(new_value - old_value)` includes both the new borrow AND the accrued interest for this obligation. This means the emode total absorbs this obligation's interest but has no mechanism to account for interest on other inactive obligations.

## Internal Pre-conditions

1. Multiple obligations need to exist in the same emode group borrowing the same asset.
2. Some obligations need to remain inactive (no borrow/repay interactions) for extended periods while interest accrues.
3. The emode group borrow limit (`emode_max_borrow_amount`) needs to be close to the actual total debt.

## External Pre-conditions

None.

## Attack Path

1. Emode group has a borrow limit of 10,000,000 USDC.
2. 100 obligations each borrow 90,000 USDC. Emode tracked total = 9,000,000.
3. Over 6 months at 10% APR, each obligation accrues ~4,500 in interest. True total debt = 9,450,000.
4. The emode counter still shows ~9,000,000 because no obligation has interacted.
5. A new borrower attempts to borrow 600,000 USDC. The emode check passes: `9,000,000 + 600,000 = 9,600,000 < 10,000,000`.
6. True total is actually 9,450,000 + 600,000 = 10,050,000, exceeding the intended limit.
7. When existing obligations interact, their interest is "caught up" and the emode total jumps, potentially blocking further borrows.

## Impact

The emode group borrow limit can be exceeded by the sum of unaccrued interest across all inactive obligations. This undermines the risk management purpose of emode borrow limits. The drift grows proportionally with: (a) total borrow volume, (b) interest rate, and (c) time since last interaction.

For a group with 10M in borrows at 10% APR with no interactions for 3 months, the drift would be ~250,000, allowing that amount of extra borrowing beyond the intended limit.

## Mitigation

Either:
1. Add an independent interest accrual mechanism to the emode group's borrow tracking that doesn't depend on individual obligation interactions.
2. When checking the emode borrow limit in `handle_borrow`, compute the true total by summing all obligations' interest-adjusted debt rather than relying on the cached counter.
3. Accept the drift as a design tradeoff but document it and set borrow limits with appropriate buffer.
