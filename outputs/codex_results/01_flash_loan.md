**Confirmed Vulnerabilities**

1. **Flash loans can farm referral qualification (bypass real-deposit intent)**
- Root cause: `repay_flash_loan_increase_referral_qualification` always credits qualification from `loan.loan_amount()` before repayment finalization, and this amount is flash-loaned principal (not sticky net deposit).  
  - [flash_loan.move:90](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/entry_points/lending/flash_loan.move:90)  
  - [flash_loan.move:119](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/entry_points/lending/flash_loan.move:119)  
  - [flash_loan.move:149](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/entry_points/lending/flash_loan.move:149)
- Attack path:
  1. Borrow flash loan.
  2. Repay via `repay_flash_loan_increase_referral_qualification`.
  3. Repeat until referral threshold is reached.
- Impact: referral code eligibility can be obtained without genuine capital commitment; referral/rebate system can be sybil-farmed at cost of flash-loan fees only.

2. **Flash loan path bypasses market outflow rate limiters**
- Root cause: normal borrow/withdraw update limiters, but flash-loan borrow/repay does not touch limiter accounting.  
  - Flash loan path: [market.move:795](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:795)  
  - Normal limiter enforcement: [market.move:349](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:349), [market.move:402](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:402)
- Attack path:
  1. Use whitelisted flash-loan caller cap.
  2. Borrow large flash loans repeatedly even when borrow/deposit outflow limiters would block normal flows.
- Impact: limiter-based throttling is ineffective for flash-loan liquidity movement (for permitted callers), weakening that control plane.

**Checks Requested: Status**

1. **Exchange rate / interest rate manipulation via flash loan:** **Not confirmed**
- Flash-loan withdraw does not modify `cash`/`debt`, so util/exchange math is not transiently skewed by flash-loan principal movement.  
  - [reserve.move:65](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:65)  
  - [reserve.move:92](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:92)  
  - [reserve.move:225](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:225)  
  - [reserve.move:318](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:318)

2. **Repayment check full amount + fee:** **Implemented correctly**
- Enforced at market layer (`amount + fee`) and reserve layer (`amount` principal + separate fee coin).  
  - [market.move:837](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:837)  
  - [reserve.move:245](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:245)

5. **Hot-potato enforcement:** **Correctly enforced**
- `FlashLoan` / `ReserveFlashLoan` have no drop/store abilities and must be consumed in-tx; asset lock also enforces one ongoing per asset.  
  - [market.move:39](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:39)  
  - [reserve.move:33](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:33)  
  - [market.move:803](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:803)  
  - [market.move:833](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:833)