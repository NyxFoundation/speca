I've thoroughly analyzed the core borrow index manipulation surface across all key files:

**Files analyzed:**
- `debt.move` - Debt struct, interest accrual per obligation
- `borrow_index.move` - Global borrow index tracking
- `reserve.move` - Reserve-level interest accrual, exchange rate, mint/burn/borrow/repay
- `interest.move` - Tri-kink interest rate model
- `obligation.move` - Obligation debt/collateral management
- `market.move` - All handler functions (borrow, repay, liquidation, withdraw, mint)
- `emode.move` - Emode group borrow tracking, update_asset_borrow
- `asset.move` - Asset configuration
- `adl.move` - Auto-deleverage registry
- `float.move` - 18-decimal fixed-point math
- `value.move` - Price/value calculations
- All lending entry points (borrow, repay, deposit, liquidate)

**Angles investigated:**
1. **Stale old values in emode `update_asset_borrow`** — The obligation's pre-accrual debt is used as the old value. This appears like a bug but is actually a correct lazy update pattern: the emode tracker also hasn't seen this obligation's interest, so using the stale value correctly catches up the delta. Verified with multi-obligation scenarios that it converges.
2. **Double interest accrual** — `refresh_obligation_borrow_interest` + `try_borrow_asset` both call `accrue_interest` on the debt, but the second call early-returns when borrow_index is unchanged. Safe.
3. **Exchange rate manipulation** — Borrow/repay don't change exchange rate (cash and debt move symmetrically). No intra-transaction manipulation possible due to same-timestamp idempotency.
4. **Rounding exploitation** — `int_mul` and `int_div` both truncate down (floor), favoring the protocol. Max rounding error is <1 unit per operation.
5. **Solvency check with stale collateral** — `handle_borrow` only refreshes borrow interest, not collateral exchange rates. This makes the check STRICTER (conservative), not exploitable.
6. **Reserve borrow check off-by-one** — `self.cash - self.cash_reserve.ceil() > amount` uses strict `>` instead of `>=`, but this only prevents borrowing the last unit of liquidity.
7. **Overflow in borrow index** — Simple interest formula bounded by Decimal's u256 range; no practical overflow risk.
8. **Interest accrual ordering** — All handler functions properly accrue interest before state-dependent checks.

NO_NEW_FINDINGS: The borrow index manipulation surface is well-implemented. Interest accrual is idempotent per timestamp, borrow index is monotonically increasing with proper assertions, debt calculations use correct proportional scaling, rounding consistently favors the protocol, and the emode lazy update pattern is mathematically correct. The only issues found (repay_fee_rate as reserve_factor, spot/ema price inconsistency) are already in the known bug list (057, 003).
