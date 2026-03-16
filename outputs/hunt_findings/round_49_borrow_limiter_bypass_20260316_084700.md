# Round 49: liquidation_sandwich

## Finding: 063 - Borrow Rate Limiter Bypass via `repay_on_behalf`

**Severity:** HIGH

**Root Cause:** `handle_repay` (market.move:483) unconditionally reduces the borrow rate limiter's outflow when processing any repayment, including `repay_on_behalf` which requires no obligation ownership. An attacker can cycle borrow → repay_on_behalf(victim) → borrow in a single PTB to repeatedly reset rate limiter capacity.

**Impact:** Attacker accumulates unbounded individual debt (up to collateral limit) in one block, bypassing the rate limiter that is the primary defense against over-borrowing during oracle instability. Also bypasses reserve-level and emode-level borrow caps since the intervening repay resets those counters too.

**Files:**
- Report: `outputs/reports/high/report_063_borrow_limiter_bypass_via_repay_on_behalf.md`
- PoC: `outputs/pocs/poc_063_borrow_limiter_bypass_via_repay_on_behalf.move`

**Key Code Paths:**
- `repay.move:33-80` — `repay_on_behalf` is public, no ownership check
- `market.move:483` — `reduce_outflow` called on borrow limiter
- `market.move:402` — `add_outflow` called on borrow limiter during borrow
- `limiter.move:100-119` — `reduce_outflow` saturates current segment at 0
