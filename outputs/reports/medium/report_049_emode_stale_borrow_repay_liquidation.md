# eMode Borrow Tracking Uses Stale Obligation Debt in `handle_repay` and `liquidation_inner`, Inflating Group Totals

## Summary

`update_asset_borrow` in both `handle_repay` and `liquidation_inner` captures the obligation's old debt amount via `unsafe_debt_amount()` **before** obligation-level interest is accrued. The stale (lower) old value causes `update_asset_borrow` to over-count the eMode group's total borrow by the accrued interest delta on every repay and liquidation event.

## Vulnerability Detail

### Root Cause

`unsafe_debt_amount()` (`debt.move:29-31`) returns the stored `Debt.amount` field without applying the current borrow index. When the obligation's `accrue_interest` has not yet been called, this value is stale — it reflects the debt as of the previous interaction, not the current interest-adjusted amount.

The `update_asset_borrow` formula in `emode.move:188` is:

```move
let new_borrow = new_value.add(*current_borrow).saturating_sub(old_value);
```

Effectively: `counter += (new_value - old_value)`. When `old_value` is stale (lower than the true post-interest value), the subtracted quantity is too small, causing the eMode counter to be inflated by the unaccounted interest delta.

### Path 1: `handle_repay` (market.move:445-494)

```move
// Line 459: Reserve interest accrued (updates borrow index)
let reserve = accrue_interest<MarketType>(name, &mut self.reserves, ...);

// Line 465: STALE — obligation interest NOT yet accrued
let obligation_old_borrow_amount = obligation.debt(name).unsafe_debt_amount();

// Line 468-469: Obligation interest accrued INSIDE repay_debt
let borrow_index = reserve.borrow_index().value();
let residule = obligation.repay_debt<MarketType, CoinType>(coin.value(), borrow_index);

// Line 473: FRESH — post-interest, post-repay amount
let obligation_new_borrow_amount = if (obligation.has_debt(name))
    obligation.debt(name).unsafe_debt_amount() else float::zero();

// Line 480: Uses stale old_value → eMode counter inflated
let emode_group_total_borrow = emode_group.update_asset_borrow(
    name, obligation_old_borrow_amount, obligation_new_borrow_amount);
```

### Path 2: `liquidation_inner` (market.move:691-793)

```move
// Line 717: STALE — obligation interest NOT yet accrued
let obligation_old_borrow_amount = obligation.debt(debt_name).unsafe_debt_amount();

// Line 720: All obligation assets' interest accrued
refresh_obligation_assets_interest(assets, emode_group, reserves, obligation, now);

// ... liquidation logic ...

// Line 783: FRESH — post-interest, post-liquidation amount
let obligation_new_borrow_amount = if (!obligation.has_debt(debt_name))
    { float::zero() } else { obligation.debt(debt_name).unsafe_debt_amount() };

// Line 784: Uses stale old_value → eMode counter inflated
emode_group.update_asset_borrow(
    debt_name, obligation_old_borrow_amount, obligation_new_borrow_amount);
```

### Numeric Example (handle_repay)

- Obligation debt before accrual: 100.0 (stored `Debt.amount`, stale)
- Obligation debt after accrual: 105.0 (5.0 interest accrued)
- User repays 50.0 tokens
- `obligation_old_borrow_amount` = 100.0 (stale)
- `obligation_new_borrow_amount` = 105.0 - 50.0 = 55.0 (fresh)
- eMode counter change: 55.0 - 100.0 = -45.0 (saturating sub → counter decreases by 45)
- **Correct** counter change should be: 55.0 - 105.0 = -50.0 (decrease by 50)
- **Drift per repay: +5.0** (the accrued interest is double-counted — once in the eMode counter, once in the obligation)

### Relationship to report_005

Report 005 ("Stale emode borrow tracking will block legitimate borrowers from borrowing") covers only the `handle_borrow` path (line 404). The present finding covers two **additional** code paths (`handle_repay` at line 465, and `liquidation_inner` at line 717) that have the identical stale-read pattern but are:

1. In different functions that require independent fixes
2. Triggered by different user actions (repay vs borrow vs liquidation)
3. Particularly impactful in the liquidation path, where many obligations are processed during market stress, compounding the drift

## Internal Pre-conditions

1. At least one obligation must have outstanding debt in an eMode group.
2. Time must have elapsed since the obligation's last interest accrual (so that `borrow_index` has advanced beyond the obligation's stored `borrow_index`).

## External Pre-conditions

None. Any user performing repay or triggering liquidation on a stale obligation produces the drift.

## Attack Path

1. Multiple obligations exist in eMode group G with asset A, total tracked borrow = 9,000,000.
2. Obligations remain idle for 3 months at 10% APR. True aggregate debt ≈ 9,225,000, but eMode counter still shows 9,000,000.
3. A liquidator liquidates an idle obligation with 100,000 debt (now 102,500 with interest).
   - `old_value` = 100,000 (stale), `new_value` = 52,500 (after seizing half)
   - Counter change: 52,500 - 100,000 → counter decreases by 47,500 (saturating sub)
   - **Correct** change: 52,500 - 102,500 = -50,000
   - Counter drift: +2,500 for this single liquidation
4. Across hundreds of liquidations during a market crash, the drift compounds: each liquidation adds `accrued_interest_delta` to the eMode counter.
5. The inflated eMode total causes `try_stop_borrow_deleverage` (line 791 in `handle_repay`, line 492 in `handle_repay`) to receive incorrect inputs, potentially preventing ADL from stopping when it should.

## Impact

The eMode group's `assets_borrows` counter systematically drifts upward from the stale-read in repay and liquidation paths. This has two effects:

1. **Premature borrow limit exhaustion**: The inflated counter can cause `emode_group_total_borrow > emode_max_borrow_amount` to trigger earlier than warranted, blocking legitimate borrows.
2. **Incorrect ADL stop conditions**: `try_stop_borrow_deleverage` receives an inflated `emode_group_total_borrow`, which may prevent the ADL mechanism from correctly stopping borrow deleveraging when the actual total has fallen below the threshold.

The drift magnitude per event is the accrued interest since the obligation's last interaction. For a 10M borrow pool at 10% APR with weekly liquidation activity, the annual drift from the liquidation path alone could reach hundreds of thousands of tokens.

## Code Snippet

- [`market.move:465`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/market.move#L465): Stale read in `handle_repay`
- [`market.move:480`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/market.move#L480): `update_asset_borrow` with stale `old_value` in `handle_repay`
- [`market.move:717`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/market.move#L717): Stale read in `liquidation_inner`
- [`market.move:784`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/market.move#L784): `update_asset_borrow` with stale `old_value` in `liquidation_inner`
- [`emode.move:183-192`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/emode.move#L183-L192): `update_asset_borrow` formula
- [`debt.move:29-31`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/debt.move#L29-L31): `unsafe_debt_amount` returns raw stored amount

## Tool used

Manual Review + Automated Analysis (SPECA Pipeline + Claude cross-validation)

## Recommendation

Move the `obligation_old_borrow_amount` read to **after** obligation-level interest accrual in both paths.

### Fix for `handle_repay` (market.move):

```move
// Line 459: Reserve interest accrued
let reserve = accrue_interest<MarketType>(name, &mut self.reserves, ...);
let borrow_index = reserve.borrow_index().value();

// Accrue obligation interest FIRST
let obligation = self.obligations.borrow_mut(obligation_id);
obligation.accrue_interest(type_name::with_defining_ids<CoinType>(), borrow_index);

// NOW read the up-to-date old amount
let obligation_old_borrow_amount = obligation.debt(name).unsafe_debt_amount();

// Then repay (skip re-accrual since already done)
let residule = obligation.unsafe_repay_debt_only<MarketType, CoinType>(coin.value());
```

### Fix for `liquidation_inner` (market.move):

```move
// Line 720: Accrue interest on all obligation assets FIRST
refresh_obligation_assets_interest(assets, emode_group, reserves, obligation, now);

// THEN read the up-to-date old amount
let obligation_old_borrow_amount = obligation.debt(debt_name).unsafe_debt_amount();
```
