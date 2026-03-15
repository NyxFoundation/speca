After thorough analysis of the flash loan mechanism and its interactions with all other protocol operations, I've traced every state transition carefully.

**Key findings from the analysis:**

1. **`flash_loan_withdraw` intentionally does NOT update `self.cash`** (reserve.move:318-324), while regular `withdraw_underlying` DOES (reserve.move:312). This means during a flash loan, `self.cash` and `underlying_balance` are inconsistent.

2. However, this is **by design** — the flash loan funds are expected to return within the same PTB. Since `self.cash` is never decremented:
   - `util_rate`, `exchange_rate`, and all interest calculations remain at their pre-flash-loan values (which IS the correct economic view since the funds are temporary)
   - No accounting field (debt, cash_reserve, total_supply, borrow_index) is affected

3. **Balance type provides a hard safety floor** — even if `self.cash` is inflated, the actual `underlying_balance.split()` will abort if insufficient real funds exist, preventing any over-withdrawal

4. **`flash_loan_lock` is per-asset** and only prevents re-entrancy of flash loans on the same asset. Other operations (borrow, repay, deposit, withdraw, liquidation) don't check this lock, but they don't need to because the accounting is consistent

5. **Flash loan fee routing is correct** — fees go to `cash_reserve` via `increase_reserve_only`, referral rebates are stored separately in the Referral module, and the final `self.cash` = `original_cash + fee_after_rebates` matches `underlying_balance`

6. **Rate limiters are not bypassed** — deposit/withdraw limiters are applied independently of flash loan state

7. **No cross-operation exploit path exists** — within a PTB, all operations between flash loan borrow and repay see consistent accounting values (since `self.cash` was never changed)

NO_NEW_FINDINGS: The flash_loan_state_inconsistency angle is exhausted. The protocol's design of NOT decrementing `self.cash` during flash loans is intentional and correct — it reflects the economic reality that funds are temporary. The Balance type's inherent safety prevents over-extraction despite the `cash`/`underlying_balance` mismatch. All accounting values (util_rate, exchange_rate, interest) compute correctly during flash loans because `self.cash` retains its pre-flash-loan value. No operation callable between flash loan borrow and repay can exploit this temporary inconsistency for profit.
