# 063: Borrow Rate Limiter Bypass via `repay_on_behalf`

### Title
Attacker will bypass borrow rate limiter via `repay_on_behalf` to accumulate unbounded debt, causing bad debt for depositors

### Summary
The `repay_on_behalf` function (public, no ownership check) calls `handle_repay` which reduces the borrow rate limiter's outflow counter via `reduce_outflow`. An attacker can cycle **borrow → repay_on_behalf(victim) → borrow** within a single Sui PTB to repeatedly reset the rate limiter's current segment, bypassing the borrow velocity cap entirely. This removes the protocol's primary defense against over-borrowing during oracle instability, enabling the attacker to accumulate unbounded individual debt (up to their collateral limit) in a single transaction.

### Root Cause
In [`market.move:483`](contracts/protocol/sources/internal/market/market.move#L483), the `handle_repay` function unconditionally reduces the borrow rate limiter's outflow:

```move
emode.borrow_mut_borrow_limiter().reduce_outflow(now, coin.value());
```

This is called for ALL repayments, including `repay_on_behalf` which requires no obligation ownership. The `reduce_outflow` function in [`limiter.move:100-119`](contracts/protocol/sources/internal/market/limiter.move#L100) only modifies the current time segment (saturating at 0):

```move
if (segment.value <= reduced_value) {
    segment.value = 0;
} else {
    segment.value = segment.value - reduced_value;
}
```

Since `borrow` (via `add_outflow`) and `repay_on_behalf` (via `reduce_outflow`) operate on the same segment within one PTB (same timestamp), the attacker can repeatedly add and then remove outflow from the current segment while old segments remain unchanged. This resets the available capacity back to `outflow_limit - old_segments_total` after each repay cycle.

Additionally, the `reserve.debt` check (`asset_max_borrow_amount`) and `emode_group_total_borrow` check (`emode_max_borrow_amount`) are also neutralized because the repay resets reserve-level debt and emode-level tracking back to pre-borrow values after each cycle.

### Internal Pre-conditions
1. Borrow rate limiter is configured and active on the emode group (standard config)
2. At least one other obligation in the same emode group has outstanding debt in the target asset (to serve as repay target)

### External Pre-conditions
1. Oracle price deviation — attacker's collateral is temporarily overvalued (natural during volatile markets, flash crashes, or oracle lag). This is the scenario the rate limiter was specifically designed to protect against.

### Attack Path
1. Attacker creates an obligation and deposits collateral (temporarily overvalued due to oracle deviation)
2. Attacker calls `borrow(7000 USDC)` → rate limiter outflow increases by 7000, reaching the limit
3. Attacker calls `repay_on_behalf(victim_obligation_id, 7000 USDC)` using borrowed coins → rate limiter outflow decreases by 7000 (back to pre-attack level)
4. Attacker calls `borrow(7000 USDC)` again → rate limiter allows it (outflow was reset)
5. Repeat steps 3-4 N times within the same PTB, targeting different victim obligations as needed
6. After N cycles: attacker holds 7000 USDC and has accumulated N×7000 debt, while rate limiter shows only 7000 outflow
7. Oracle corrects → attacker's collateral value drops → attacker's debt far exceeds collateral → bad debt for protocol

All steps execute atomically in a single Sui Programmable Transaction Block (PTB). Each `borrow` call passes the `is_obligation_safe` check because the collateral is still overvalued during the PTB. The rate limiter, emode borrow limit, and reserve borrow limit are all neutralized by the intervening repay.

### Impact
The depositors (liquidity providers) suffer loss equal to the attacker's accumulated debt minus their actual collateral value after oracle correction. Without the bypass, the rate limiter would cap exposure to `outflow_limit` per cycle (e.g., $100K/day). With the bypass, exposure equals the attacker's full collateral-supported borrowing capacity (potentially $10M+ in a single block). The delta is the additional bad debt directly attributable to the rate limiter bypass.

Example: Rate limit = $100K/day. Attacker's (inflated) collateral supports $5M at 80% LTV. Without bypass: max $100K bad debt exposure. With bypass: $5M bad debt exposure. If oracle corrects by 30%, bad debt = $5M - $3.5M = $1.5M.

### PoC
See `poc_063_borrow_limiter_bypass_via_repay_on_behalf.move`

### Mitigation
Option A (recommended): Do NOT reduce the borrow rate limiter on repayment. The rate limiter should be one-directional (only counts borrows, never decremented). This is the simplest fix:

```move
// In handle_repay, REMOVE this line:
// emode.borrow_mut_borrow_limiter().reduce_outflow(now, coin.value());
```

Option B: Only reduce the limiter when the repayer is the obligation owner (i.e., not `repay_on_behalf`):

```move
// Add a flag parameter to handle_repay to distinguish owner repay vs on_behalf
if (is_obligation_owner) {
    emode.borrow_mut_borrow_limiter().reduce_outflow(now, coin.value());
}
```

Option C: Track outflow per-obligation rather than globally per-emode-group, so one obligation's repay cannot free capacity for another.
