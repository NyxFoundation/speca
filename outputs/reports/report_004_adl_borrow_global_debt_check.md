# ADL operator will unfairly liquidate healthy emode group users due to global debt check

## Summary

`handle_debt_auto_deleverage` checks the protocol-wide total debt via `reserves.load_by_type(debt_type).debt()` instead of the emode-group-specific borrow amount, causing obligations in healthy emode groups to be liquidated under ADL parameters when other emode groups drive the total above the threshold.

## Root Cause

In [`market.move:580-582`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L580-L582), the borrow ADL activation check uses the **global reserve debt**:

```move
let total_debt = (*self.reserves.load_by_type(debt_type).debt()).floor();
debt_params.ensure_limit_breached(total_debt);
```

However, borrow ADL is registered **per-emode-group** at [`market.move:575`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L575):

```move
let timelock = *adl_registry.get_borrow_deleverage(debt_type, emode_group_id);
```

And the stop condition at [`market.move:685-688`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L685-L688) correctly uses the **emode-group-specific** borrow amount:

```move
let total_borrow = emode_group.borrow_amount(debt_type).floor();
adl.try_stop_borrow_deleverage<DebtType>(..., total_borrow);
```

This inconsistency means the activation check (global) and stop check (emode-specific) use different scopes.

## Internal Pre-conditions

1. The same debt token (e.g., USDC) needs to be borrowed across multiple emode groups.
2. An ADL borrow deleverage needs to be registered for the target emode group with a `target_amount` threshold.
3. The sum of borrows across all emode groups needs to exceed `target_amount`, even if the target emode group's own borrows are below it.

## External Pre-conditions

None. This is a code logic error.

## Attack Path

1. Admin configures borrow ADL for USDC in emode_group_0 with `target_amount = 1,000,000`.
2. Emode_group_0 has 400,000 USDC in borrows. Emode_group_1 has 800,000 USDC in borrows. Total protocol USDC debt = 1,200,000.
3. ADL operator calls `liquidate_adl_borrow` targeting an obligation in emode_group_0.
4. `ensure_limit_breached(1,200,000)` passes because `1,000,000 < 1,200,000`.
5. The obligation in emode_group_0 is liquidated under ADL's relaxed LTV parameters despite emode_group_0's borrows (400,000) being well below the 1,000,000 target.
6. Additionally, `try_stop_borrow_deleverage` immediately triggers because emode_group_0's borrow amount (now reduced) is even further below `target_amount`, creating an inconsistent state.

## Impact

Users in emode groups with healthy borrow levels suffer unwarranted ADL liquidation because other emode groups' debt pushes the global total above the threshold. ADL liquidation uses relaxed LTV parameters and can liquidate positions that are fully healthy under normal conditions, causing unjustified collateral loss. The severity is proportional to the gap between the targeted emode group's actual borrows and the ADL target amount.

## PoC

The inconsistency is visible by comparing two adjacent code blocks:

**Activation** (`handle_debt_auto_deleverage`, line 580):
```move
let total_debt = (*self.reserves.load_by_type(debt_type).debt()).floor();  // GLOBAL
debt_params.ensure_limit_breached(total_debt);
```

**Stop** (`try_stop_borrow_deleverage`, line 686):
```move
let total_borrow = emode_group.borrow_amount(debt_type).floor();  // EMODE-SPECIFIC
adl.try_stop_borrow_deleverage<DebtType>(..., emode_group_id, total_borrow);
```

Compare with collateral ADL (`handle_collateral_auto_deleverage`, line 649) which correctly uses emode-group-independent reserve data for both activation and stop, since collateral deposits are shared across emode groups.

## Mitigation

Replace the global debt check with the emode-group-specific borrow amount:

```move
// Before (line 580-582):
let total_debt = (*self.reserves.load_by_type(debt_type).debt()).floor();
debt_params.ensure_limit_breached(total_debt);

// After:
let total_borrow = emode_group.borrow_amount(debt_type).floor();
debt_params.ensure_limit_breached(total_borrow);
```

This aligns the activation check scope with the stop check scope and the ADL registry's per-emode-group design.
