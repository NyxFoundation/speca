After thorough analysis of the flash loan mechanism and its interactions with other protocol components, I've systematically examined every potential state inconsistency vector:

**Key observations:**

1. **`cash` vs `underlying_balance` mismatch during flash loan**: `flash_loan_withdraw` (reserve.move:318-324) does NOT update `self.cash`, while it DOES split from `underlying_balance`. This creates a temporary desync. However:
   - Both borrow and repay skip `cash` updates (symmetric), so they cancel out
   - Move's `Balance` type prevents actual over-withdrawal at the runtime level
   - Exchange rate `(cash + debt - cash_reserve) / total_supply` is UNCHANGED during the flash loan (correct for atomic operations)
   - Utilization rate is also unchanged

2. **No operations blocked during flash loan**: `flash_loan_lock` only prevents nested flash loans on the same asset. Deposit, withdraw, borrow, repay, liquidate can all execute during a flash loan. However, none can exploit the stale `cash` because the actual `Balance` object enforces invariants.

3. **Interest accrual not affected**: Flash loans don't change `cash`, so `accrue_interest` calculates the same rate regardless.

4. **Rate limiters**: Not updated for flash loans (correct - atomic operations have zero net flow).

5. **ADL interaction**: Inflated `cash` during flash loan makes `cash_plus_borrows_minus_reserves` higher, which is the conservative direction (keeps deleverage active longer).

6. **Referral rebate accounting**: Correctly tracks rebates, remaining fee > 0 enforced, cash/underlying stay in sync after repay.

7. **Fee emode selection**: Known bug #050 already covers the ability to pick the lowest fee rate emode group.

NO_NEW_FINDINGS: Flash loan implementation is well-designed with symmetric cash-skip on borrow/repay, hot potato atomicity, per-asset reentrancy guard, and Move's Balance type safety preventing exploitation of the temporary cash/underlying desync. All interaction paths with deposit, withdraw, borrow, liquidation, ADL, and limiters are safe.
