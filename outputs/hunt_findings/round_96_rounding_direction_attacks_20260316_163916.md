NO_NEW_FINDINGS: The protocol uses 18-decimal fixed-point arithmetic (WAD=1e18) with consistently protocol-favorable rounding throughout all critical paths. Deposits and withdrawals use `floor` against the user, liquidation seize uses `floor` against the liquidator, debt repayment uses `ceil` against the borrower, and solvency checks use full Decimal precision without floor/ceil. The maximum rounding error per operation is 1 unit of the smallest token denomination, with no accumulation path that could reach >$10 or >1% loss. All potentially exploitable rounding issues found are already in the known bugs list (#028 dust obligations, #050 flash loan fee bypass, #057 repay_fee_rate misuse).
, handle_liquidation, liquidation_inner, solvency checks
- `contracts/protocol/sources/internal/market/interest.move` — tri-kink rate model
- `contracts/protocol/sources/internal/market/asset.move` — AssetConfig
- `contracts/protocol/sources/internal/market/borrow_index.move` — borrow index tracking
- `contracts/protocol/sources/internal/value.move` — coin_value helper
- `contracts/protocol/sources/entry_points/lending/*.move` — all entry points

## Rounding Inventory

| Operation | Function | Rounding | Direction |
|-----------|----------|----------|-----------|
| Deposit (mint ctokens) | `int_div(amount, exchange_rate)` | floor | Against user |
| Withdraw (burn ctokens) | `exchange_rate.int_mul(ctokens)` | floor | Against user |
| Liquidation seize calc | `seize_ctokens.floor()` | floor | Against liquidator |
| Liquidation ctoken cap refund | `.ceil()` on expected_repay | ceil | Against liquidator |
| Liquidation ctoken to underlying | `exchange_rate.int_mul(ctokens)` | floor | Against liquidator |
| Full debt repay (obligation) | `debt.unsafe_debt_amount().ceil()` | ceil | Against borrower |
| Reserve debt repay | `self.debt.sub(from(coin_value))` | exact | N/A |
| Flash loan fee | `fee_rate.int_mul(amount)` | floor | Against protocol (bounded by 1 unit) |
| Solvency check | Decimal arithmetic | 18-digit precision | No floor/ceil applied |
| Interest accrual | Decimal arithmetic | 18-digit precision | Negligible |
| Exchange rate | Decimal division | 18-digit precision | Negligible |

## Detailed Analysis

### 1. Deposit/Withdraw Rounding
Both operations round against the user (floor). The dust stays in the reserve, marginally increasing exchange_rate for remaining depositors. Not exploitable — repeated deposit/withdraw loses money for the attacker.

### 2. Zero Ctoken Mint
When exchange_rate > 1, depositing very small amounts can yield int_div(small, rate) = 0 ctokens. The tokens are absorbed. However: requires user error, no forced attack vector on Sui, standard vault design.

### 3. Liquidation Seize Floor
liquidate_calculate_seize_ctokens returns floor(seize_ctokens). Liquidator gets fewer ctokens. Impact is at most 1 ctoken per liquidation. Loss is borne by the liquidator who voluntarily initiated.

### 4. Obligation vs Reserve Debt Drift
When obligation fully repays, ceil(individual_debt) is subtracted from reserve.debt. Since actual debt < ceil(debt), reserve.debt decreases by up to 1 extra unit per full repay. Negligible accumulation.

### 5. Emode Group Borrow Staleness
Emode group borrow tracking is lazy-updated. Makes emode borrow limit slightly more permissive. Design choice, not rounding.

### 6. Flash Loan Fee Floor
fee = floor(rate * amount) rounds down by at most 1 unit. Already covered by known bug #050.

## Conclusion
The protocol uses 18-decimal fixed-point arithmetic throughout. All critical rounding operations favor the protocol/depositors over users/liquidators/borrowers. No accumulation path exists that would result in >1% or >$10 loss for affected users.

## Result
NO_NEW_FINDINGS
