NO_NEW_FINDINGS: The liquidation sandwich angle is exhausted. After thorough analysis of the entire liquidation flow (liquidation_inner, seize calculation, solvency checks, flash loan interactions, rate limiters, ADL, oracle prices, rounding), all potential issues map to already-known bugs (#003 spot/EMA inconsistency, #062 bad debt, #028 dust obligations, #057 repay_fee_rate). The Sui object model structurally prevents traditional sandwich attacks (no mempool, sequential shared-object access), flash loans cannot manipulate exchange rates (self.cash is not updated during flash loan), and all arithmetic rounding favors the protocol/borrower.
ging activation/deactivation
- `limiter.move` - rate limiter add_outflow/reduce_outflow
- `float.move` - precision of int_mul, int_div, floor, ceil
- `x_oracle.move`, `user_oracle.move`, `pyth_adaptor.move` - oracle prices
- All lending entry points (liquidate, deposit, borrow, withdraw, repay, flash_loan)

### Attack Vectors Explored

1. **Flash loan + exchange rate manipulation**: Flash loans don't update self.cash, so exchange rate unaffected
2. **EMA vs spot price in liquidation**: Already known #003
3. **Rate limiter bypass via repay_on_behalf**: Net borrowing still limited by solvency checks
4. **Close factor bypass at bad debt threshold**: By design, known via #062
5. **Interest accrual timing in liquidation_inner**: Pre-interest old_value in emode tracking is correct
6. **Rounding in seize/repay**: Floor for ctokens, ceil for repay - favors protocol/borrower
7. **Sui object model**: Prevents traditional mempool sandwich attacks
