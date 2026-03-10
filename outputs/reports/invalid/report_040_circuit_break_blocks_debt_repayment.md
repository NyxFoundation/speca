# Circuit Break Prevents Repayment and Can Force Debt Deterioration

## Summary
When circuit break is active, repayment paths are fully blocked. Borrowers cannot reduce principal or interest exposure during emergencies, which can accelerate insolvency and bad debt instead of containing risk.

## Vulnerability Detail
`repay_on_behalf` hard-reverts under circuit break:

- `assert!(!market.has_circuit_break_triggered(), market_under_circuit_break)`

Both public repayment APIs (`repay_on_behalf`, `repay`) route through this guard, so no debt reduction is possible while circuit break remains enabled.

In stressed conditions, debt continues to accrue over time (interest model and reserve accrual remain part of protocol state progression when actions resume), but users are denied the one operation that would reduce risk: repayment.

This is a safety-control inversion: emergency mode should typically allow risk-reducing actions (repay/deleverage), while blocking risk-increasing actions.

## Impact
- Borrowers cannot repay during emergency periods
- Health factors can worsen over time without a mitigation path
- Protocol may accumulate additional bad debt after circuit-break windows
- Incident response becomes operationally brittle because a protective control blocks debt reduction

## Code Snippet
- `contracts/protocol/sources/entry_points/lending/repay.move:33-45`
- `contracts/protocol/sources/entry_points/lending/repay.move:94-103`
- `contracts/protocol/sources/internal/market/market.move:445-494` (repayment core path only reachable if entrypoint guard passes)

## Tool used
Manual Review + Automated Analysis

## Recommendation
Allow repayment during circuit break, while keeping borrow/withdraw/flash-loan restricted.

Suggested approach:

```move
// repay.move
// remove circuit-break rejection for repay paths
// keep market/version validation, then execute handle_repay normally
```

If needed, add a dedicated emergency policy flag (e.g., `repay_paused`) instead of reusing global circuit break for all actions.
