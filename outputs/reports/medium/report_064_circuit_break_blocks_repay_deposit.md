### Circuit breaker unnecessarily blocks repay and deposit, causing unfair interest accrual and worsening protocol insolvency

### Summary

The circuit breaker mechanism blocks ALL protocol operations including beneficial ones (repay, deposit), which will cause unfair interest accumulation for borrowers and prevent depositors from adding liquidity during emergencies, worsening the protocol's position when the circuit break is lifted.

### Root Cause

In every entry point file, the same circuit breaker check is applied indiscriminately:

- [`repay.move:44`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/lending/repay.move#L44): `assert!(!market.has_circuit_break_triggered(), ...)`
- [`deposit.move:44`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/lending/deposit.move#L44): `assert!(!market.has_circuit_break_triggered(), ...)`

Repay and deposit are **risk-reducing operations** — they decrease debt and increase liquidity respectively. Blocking them during a circuit break is counterproductive and harmful. In contrast, industry-standard lending protocols (Compound, Aave) never block repay, even during emergencies.

### Internal Pre-conditions

1. Admin needs to call `trigger_circuit_break` to activate the circuit breaker.

### External Pre-conditions

1. Market conditions need to be severe enough for admin to trigger the circuit breaker (e.g., oracle issues, exploit detection).

### Attack Path

1. Admin triggers circuit breaker due to market emergency (e.g., suspected oracle manipulation).
2. During circuit break (could last hours or days):
   - Borrowers CANNOT repay their debt, even though they want to.
   - Interest continues accruing on ALL outstanding debt via the borrow index.
   - Depositors CANNOT add liquidity to improve the protocol's reserve ratio.
   - Liquidators CANNOT liquidate underwater positions (already reported as #031).
3. Admin lifts circuit breaker.
4. Borrowers now owe significantly more than before the circuit break due to accumulated interest they could not avoid.
5. Some positions that were healthy before the circuit break are now liquidatable due to accumulated interest.
6. Positions that went underwater during the circuit break have become bad debt (#062).

### Impact

Borrowers suffer unfair interest charges proportional to the duration of the circuit break and the interest rate. For a 24-hour circuit break at 5% APY on $1M of outstanding debt, the unfair interest is approximately $137. For higher rates or longer durations, the impact scales linearly. Additionally, the inability to deposit during emergencies prevents beneficial liquidity injection that could stabilize the protocol.

Combined with #031 (liquidation blocked) and #062 (bad debt not socialized), the overly aggressive circuit breaker creates a cascade: emergency → freeze → bad debt → insolvency → bank run.

### PoC

```move
// The circuit breaker blocks ALL operations including repay and deposit.
// This can be verified by examining the entry points:
//
// repay.move:44:    assert!(!market.has_circuit_break_triggered(), ...)
// deposit.move:44:  assert!(!market.has_circuit_break_triggered(), ...)
// borrow.move:47:   assert!(!market.has_circuit_break_triggered(), ...)
// withdraw.move:47: assert!(!market.has_circuit_break_triggered(), ...)
// liquidate.move:59: assert!(!market.has_circuit_break_triggered(), ...)
// flash_loan.move:132: assert!(!market.has_circuit_break_triggered(), ...)
// enter_market.move:47: assert!(!market.has_circuit_break_triggered(), ...)
//
// In Compound V2 (the reference implementation), repay is NEVER blocked:
// - CToken.repayBorrow() has no pause check
// - CToken.repayBorrowBehalf() has no pause check
// Only borrow, mint (deposit), and transfer can be paused individually.
```

### Mitigation

Remove the circuit breaker check from `repay.move` and `deposit.move`. These are risk-reducing operations that should always be permitted:

```move
// repay.move — REMOVE this line:
// assert!(!market.has_circuit_break_triggered(), protocol::error::market_under_circuit_break());

// deposit.move — REMOVE this line:
// assert!(!market.has_circuit_break_triggered(), protocol::error::market_under_circuit_break());
```

Alternatively, implement a granular pause mechanism (similar to the per-asset pause in `asset.move`) where each operation type can be individually paused.
