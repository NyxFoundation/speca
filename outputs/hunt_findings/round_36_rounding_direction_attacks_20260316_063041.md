After thorough analysis of all rounding-sensitive code paths in the protocol, here's my assessment:

## Analysis Summary

**Math library (`float.move`):** Uses 18-decimal fixed-point arithmetic (WAD = 1e18) with u256 intermediates. Provides high precision. `floor()`, `ceil()`, `int_mul` (floor), `int_div` (floor) are all correctly implemented.

**Rounding directions analyzed:**

| Operation | Function | Rounding | Direction |
|-----------|----------|----------|-----------|
| Deposit (mint ctokens) | `int_div(amount, exchange_rate)` | floor | Protocol-favorable |
| Withdraw (burn ctokens) | `exchange_rate.int_mul(ctokens)` | floor | Protocol-favorable |
| Liquidation seize calc | `seize_ctokens.floor()` | floor | Borrower-favorable (conservative) |
| Liquidation ctoken redeem | `exchange_rate.int_mul(ctokens)` | floor | Protocol-favorable |
| Protocol liquidation fee | `liq_revenue_factor.int_mul(amount)` | floor | Liquidator-favorable (< 1 unit) |
| Debt repay ceiling | `debt.unsafe_debt_amount().ceil()` | ceil | Protocol-favorable |
| Liquidation repay cap | `obligation_debt.ceil()` | ceil | Protocol-favorable |
| Solvency check | Decimal comparison (ge) | exact | N/A (18 decimal precision) |
| Debt accrual | `amount * new_index / old_index` | truncate | < 1e-18 per accrual |
| Emode borrow tracking | `saturating_sub` on Decimals | exact | N/A |

**Specific attack vectors considered:**
1. **Repeated small deposit/withdraw to extract rounding dust** - Both mint and burn round against the user, so repeated operations lose dust TO the protocol, not from it.
2. **First depositor attack** - Exchange rate starts at 1.0 and there's no efficient way to inflate it (no donation path that increases the numerator).
3. **Liquidation residual discrepancy** - `_residual` from `unsafe_repay_debt_only` is discarded in `liquidation_inner` (line 774), but the prior refund calculation (lines 734-743) already caps repay to `ceil(debt)`, making residual effectively 0.
4. **Reserve debt vs obligation debt drift** - When `ceil(obligation_debt)` tokens are repaid to the reserve, the reserve debt is reduced by up to 1 more unit than the obligation's actual debt contribution. This is < 1 unit per liquidation (~$0.000001 for 6-decimal tokens).
5. **Zero ctoken mint** - If exchange_rate > deposit_amount, mint returns 0 ctokens. But this is self-harm (user donates tokens) and the `assert!(collateral_amount > 0)` doesn't prevent it.
6. **Close factor rounding bypass** - Close factor check uses Decimal comparison with 18-decimal precision, effectively exact.

NO_NEW_FINDINGS: The protocol's 18-decimal fixed-point arithmetic provides sufficient precision for all operations. Rounding directions are consistently protocol-favorable (floor on mint/burn/seize, ceil on debt comparison). All identified rounding errors are < 1 unit per operation, which for tokens with 6+ decimals amounts to < $0.01 per operation. No exploitable accumulation pattern exists that meets the Sherlock HIGH threshold (>1% and >$10 loss). The known bugs (#028, #032, #050, #057) already cover the main rounding-adjacent issues.
