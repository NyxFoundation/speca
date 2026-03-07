Confirmed findings on interest accrual:

1. **Simple-interest accrual (not true compounding between updates)**  
Root cause: [`reserve.move` lines 118-121, 139-146](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:118), [`debt.move` line 25](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/debt.move:25).  
Attack path: keep market mostly idle; interest is applied as `r * dt` (linear) on update, not per-second exponential compounding over `dt`.  
Impact: systematic under-accrual vs a true compound-rate interpretation, reducing lender yield/protocol revenue (economic mismatch).

2. **Utilization can exceed 1.0; borrow rate can exceed configured max; can also hard-revert**  
Root cause: [`util_rate` uses `debt / (debt + cash - cash_reserve)`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:65), with no clamp; [`calc_interest` extrapolates above 1.0](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/interest.move:85); `cash_reserve` grows during accrual without cash inflow ([`reserve.move` line 143](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:143)).  
Attack path: high debt + low cash + growing `cash_reserve` => denominator shrinks below debt (util > 1), or below zero (u256 sub underflow in `cash_plus_borrows_minus_reserves`).  
Impact: interest-rate runaway beyond `max_borrow_rate`, possible overflow/DoS on accrual-sensitive operations.

3. **Reserve debt vs sum(obligation debts) divergence from precision loss**  
Status: **not confirmed as exploitable vulnerability**.  
Reason: both sides are index-based and updated consistently on borrow/repay paths; precision loss exists (flooring in [`float.move` mul/div](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/math/sources/float.move:72)), but appears to be dust-scale and bounded by 1e-18 decimal precision. I do not see a concrete profit extraction path from this alone.

4. **`take_revenue` does not accrue interest first**  
Root cause: admin entry calls market take directly ([`entry_points/admin/revenue.move` line 47](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/entry_points/admin/revenue.move:47)); market wrapper directly calls reserve take ([`market.move` lines 212-219](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:212)); reserve take only subtracts `cash_reserve` ([`reserve.move` lines 257-263](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:257)).  
Attack path: revenue withdrawal can happen against stale reserve accounting (no `accrue_interest` call).  
Impact: stale/under-collected protocol revenue and accounting mismatch at withdrawal time.

5. **Interest-accrual timing arbitrage (same-second zero-interest window)**  
Root cause: timestamps are second-granularity ([`borrow.move` line 49](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/entry_points/lending/borrow.move:49), [`repay.move` line 46](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/entry_points/lending/repay.move:46)); accrual is skipped when `last_updated == now` ([`reserve.move` lines 132-135](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:132)).  
Attack path: borrow and repay within the same second (or after an accrual already happened in that second) => zero incremental interest.  
Impact: fee-free short-horizon borrowing behavior and interest leakage; can undercut intended borrowing cost/flash-loan economics for very short durations.