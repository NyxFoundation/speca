**Confirmed Vulnerabilities**

1. **`take_revenue` does not accrue interest first (stale reserve accounting)**
- Root cause: [`/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/entry_points/admin/revenue.move:47`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/entry_points/admin/revenue.move:47), [`/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:212`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:212), [`/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:218`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:218).  
- `take_revenue` directly withdraws `cash_reserve` without calling market `accrue_interest` path (implemented at [`market.move:1015`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:1015)).  
- Attack path: revenue collection can be performed against stale reserve state before any user action triggers accrual, causing under-collection at withdrawal time.  
- Impact: protocol revenue extraction is delayed/under-realized per collection event (economic accounting bug; not direct theft).

2. **Borrow off-by-one liquidity check (`>` instead of `>=`)**
- Root cause: [`/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:197`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:197).  
- Available borrowable cash is checked as `self.cash - self.cash_reserve.ceil() > amount`, so exact-max borrow always reverts.  
- Attack path: borrower requests exactly the computed available amount; transaction fails.  
- Impact: 1-unit liquidity gets permanently unusable for this path; can cause edge-case borrow/automation failures (availability/capital-efficiency bug).

3. **`repay_amount` full-close rounding can overcharge payer by up to 1 unit**
- Root cause: [`/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:206`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:206) and [`reserve.move:207`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:207).  
- On `repay_amount > debt`, it uses `debt.ceil()` for settlement boundary.  
- Attack path: repayer trying to close a fractional debt must pay integer coin amount; rounding forces payment up to `<1` extra unit versus exact debt.  
- Impact: deterministic user overpayment on close-outs; aggregate economic leakage from repayers.

**Not Confirmed as Vulnerability (from your checklist)**

1. **Flash loan fee routing (protocol vs depositors):** confirmed behavior routes fee to protocol reserve (`cash_reserve`) at [`reserve.move:253`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:253), with fee computed in [`market.move:813`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:813). This appears intentional design, not an exploit by itself.
2. **Cash invariant correctness:** no end-state break found in these paths. Flash-loan withdraw does not decrement `self.cash` (see [`reserve.move:318`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:318)), but repayment restores underlying balance in-tx and hot-potato repayment constraints prevent committing unpaid states.