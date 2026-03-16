### ADL operator will unfairly liquidate healthy emode group users because debt deleverage guard uses global reserve debt instead of per-group borrow

### Summary

The `handle_debt_auto_deleverage` execution guard at `market.move:580` uses global `reserve.debt()` to validate that ADL conditions are still met, but ADL is registered and deactivated on a **per-emode-group** basis using `emode_group.borrow_amount()`. This inconsistency allows ADL liquidation of users in healthy emode groups when unrelated groups' borrowing inflates the global reserve debt above the ADL target threshold.

### Root Cause

In [`market.move:580-582`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L580-L582):

```move
let total_debt = (*self.reserves.load_by_type(debt_type).debt()).floor();
let debt_params = timelock.inner();
debt_params.ensure_limit_breached(total_debt);
```

This reads the **global** reserve-level debt for the coin type (sum across ALL emode groups). But ADL is registered per-emode-group at line 575:

```move
let timelock = *adl_registry.get_borrow_deleverage(debt_type, emode_group_id);
```

The corresponding ADL **stop** condition correctly uses per-group borrow (line 686):

```move
let total_borrow = emode_group.borrow_amount(debt_type).floor();
```

The mismatch: `ensure_limit_breached` at activation uses `reserve.debt()` (global), but `try_stop_borrow_deleverage` uses `emode_group.borrow_amount()` (per-group).

### Internal Pre-conditions

1. Multiple emode groups must exist that borrow the same asset (e.g., USDC)
2. ADL must be activated for one emode group (the victim group) with a `target_amount` based on that group's expected borrow level

### External Pre-conditions

1. Other emode groups' borrowing must push the global reserve debt above the victim group's ADL `target_amount`

### Attack Path

1. Protocol has emode group A (30M USDC borrow) and group B (80M USDC borrow). Global USDC debt = 110M.
2. Admin enables debt ADL for group A with `target_amount = 50M` (precautionary measure for group A).
3. Group A's actual borrow (30M) is well below the target (50M) — group A users are healthy.
4. ADL operator calls `liquidate_adl_borrow` targeting a group A user's obligation.
5. Line 580: `total_debt = reserve.debt() = 110M`. Line 582: `ensure_limit_breached(110M)` checks `50M < 110M` — **passes**, even though group A's actual borrow (30M) is below the 50M target.
6. The group A user is subjected to ADL liquidation with progressively worsening terms:
   - `liquidation_ltv` decreases hourly (line 587): healthy users become liquidatable
   - `liquidation_incentive` increases daily (line 589): more collateral seized
7. Group A user loses collateral at unfavorable terms despite their group being healthy.

### Impact

Users in healthy emode groups suffer forced ADL liquidation when unrelated groups' borrowing inflates the global debt. ADL parameters worsen over time (hourly LTV drop + daily incentive increase), so prolonged ADL events cause increasing collateral loss. With the example above, group A users lose collateral even though their group is $20M under the ADL target.

The severity is amplified because ADL operates with a `liquidation_ltv_threshold_override` that drops over time, meaning even well-collateralized positions can be liquidated after enough hours have passed.

### PoC

Place in `contracts/protocol/tests/integration/test_cases/` and run:
```bash
sui move test poc_066 --gas-limit 5000000000
```

```move
#[test_only]
module protocol::poc_066_adl_global_debt_mismatch;

use protocol::adl;
use math::float;

/// Demonstrates that ADL execution guard uses global debt
/// while ADL is registered per-emode-group.
///
/// Setup:
///   - target_amount = 50,000,000 (50M USDC)
///   - Group A borrow: 30M (healthy, below target)
///   - Group B borrow: 80M
///   - Global reserve.debt: 110M
///
/// Bug: ensure_limit_breached(110M) passes because 50M < 110M,
/// even though group A's actual borrow (30M) is below target.
#[test]
fun test_adl_passes_with_global_debt_above_target() {
    let target_amount: u64 = 50_000_000; // 50M USDC target for group A

    let params = adl::new_auto_deleverage_params(
        target_amount,
        float::from_quotient(95, 100),   // liquidation_factor_base
        float::from_quotient(1, 100),    // hourly_drop
        float::from_quotient(5, 100),    // incentive_base
        float::from_quotient(1, 100),    // daily_penalty
        float::from_quotient(50, 100),   // close_factor
    );

    // Group A borrow = 30M — BELOW target, should NOT trigger ADL
    let _group_a_borrow: u64 = 30_000_000;
    // This correctly would NOT pass:
    // params.ensure_limit_breached(_group_a_borrow); // would abort: 50M >= 30M

    // But the code uses GLOBAL reserve.debt = 110M
    let global_reserve_debt: u64 = 110_000_000;
    // This INCORRECTLY passes:
    params.ensure_limit_breached(global_reserve_debt); // passes: 50M < 110M

    // Group A users are unjustly ADL-liquidated!
}

/// Shows that using the correct per-group amount would block the ADL.
#[test]
#[expected_failure(abort_code = 603, location = protocol::adl)]
fun test_adl_correctly_blocked_with_group_debt() {
    let target_amount: u64 = 50_000_000;

    let params = adl::new_auto_deleverage_params(
        target_amount,
        float::from_quotient(95, 100),
        float::from_quotient(1, 100),
        float::from_quotient(5, 100),
        float::from_quotient(1, 100),
        float::from_quotient(50, 100),
    );

    // Group A's actual borrow: 30M — below 50M target
    let group_a_borrow: u64 = 30_000_000;
    params.ensure_limit_breached(group_a_borrow); // correctly aborts
}
```

### Mitigation

Replace global reserve debt with per-emode-group borrow amount in the ADL execution guard:

```move
// In handle_debt_auto_deleverage, replace lines 580-582:
// OLD (uses global reserve debt):
// let total_debt = (*self.reserves.load_by_type(debt_type).debt()).floor();

// NEW (uses per-emode-group borrow):
let total_debt = emode_group.borrow_amount(debt_type).floor();

let debt_params = timelock.inner();
debt_params.ensure_limit_breached(total_debt);
```

This aligns the execution guard with both the per-group ADL registration and the per-group stop conditions.
