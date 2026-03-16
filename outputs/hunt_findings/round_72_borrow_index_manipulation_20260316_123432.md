After thorough analysis of the borrow index mechanism, I've examined:

1. **debt.move**: Borrow index tracking per-obligation, interest accrual formula `amount * new_index / old_index` - correct with proper monotonicity checks
2. **borrow_index.move**: Global index with time tracking, monotonic enforcement
3. **reserve.move**: Reserve-level interest accrual using simple interest per-period compounding, exchange rate computation, borrow/repay/liquidation flows
4. **obligation.move**: Per-obligation debt tracking, borrow/repay with interest accrual
5. **market.move**: Full borrow/repay/liquidation/withdraw flows, solvency checks, emode group borrow tracking
6. **interest.move**: Tri-kink interest rate model
7. **float.move**: 18-decimal fixed-point math (u256 backing)
8. **Entry points**: borrow.move, repay.move wrapper validation

Key findings from analysis:

- **Emode total borrow tracking uses stale obligation amounts** (pre-accrual old vs post-accrual new in `update_asset_borrow`) — but this is correct lazy accounting since the stale value matches what the emode total last recorded for that obligation
- **Collateral interest not accrued during borrow** — by design (conservative, noted in comments)
- **Flash loan doesn't update `self.cash`** — safe because actual `underlying_balance.split()` prevents over-extraction
- **`repay_fee_rate` used as `reserve_factor`** — already known bug #057
- **Borrow index grows during zero-debt periods** — benign, ratio-based accrual means absolute index value doesn't matter
- **Rounding in `debt.debt()` favors borrowers** — at most 1e-18 per operation, negligible
- **`ceil()` in repay residual** — at most 1 unit loss per repay, dust-level

All potential borrow index manipulation vectors lead to either:
- No impact (correct by design)
- Conservative behavior (over-counting debt / under-counting collateral)
- Dust-level rounding (< 1 unit)

NO_NEW_FINDINGS: The borrow index mechanism is well-implemented with proper monotonicity enforcement, consistent interest accrual between reserve and obligation levels, correct lazy emode tracking, and conservative solvency checks. No exploitable path to manipulate the borrow index for direct fund loss >1%.
