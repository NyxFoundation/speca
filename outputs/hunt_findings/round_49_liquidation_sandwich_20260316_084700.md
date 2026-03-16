## Finding: 063 - Borrow Rate Limiter Bypass via `repay_on_behalf`

**Severity: HIGH**

### Summary

The `repay_on_behalf` function is fully public (no obligation ownership required) and calls `handle_repay` which reduces the borrow rate limiter's outflow counter. An attacker can exploit this by cycling **borrow → repay_on_behalf(victim) → borrow** within a single Sui PTB to repeatedly reset the rate limiter, bypassing it entirely.

### Root Cause

In `market.move:483`, `handle_repay` unconditionally calls `reduce_outflow` on the borrow rate limiter. Since `repay_on_behalf` requires no `ObligationOwnerCap`, anyone can trigger this reduction by repaying another user's debt with their own borrowed coins.

### Attack Flow (single PTB, same timestamp)

1. Attacker borrows 7000 USDC → limiter at capacity (10000)
2. Attacker calls `repay_on_behalf(victim, 7000)` → limiter reset to 3000
3. Attacker borrows 7000 USDC again → limiter at capacity (10000)
4. Repeat N times → attacker accumulates N×7000 debt

The `reserve.debt`, `emode_group_total_borrow`, and rate limiter are ALL neutralized because each repay resets them. Only the collateral safety check constrains the attacker — but if collateral is temporarily overvalued (oracle lag), the attacker drains far more than the rate limiter was designed to permit.

### Files
- **Report:** `outputs/reports/high/report_063_borrow_limiter_bypass_via_repay_on_behalf.md`
- **PoC:** `outputs/pocs/poc_063_borrow_limiter_bypass_via_repay_on_behalf.move` (unit test on limiter module — passes to demonstrate the bypass, with a second test showing the limiter correctly blocks without bypass)
