# Liquidator will extract excess collateral from borrowers due to spot/EMA price inconsistency

## Summary

`liquidate_calculate_seize_ctokens` uses `get_spot_price` for collateral seizure calculation while `ensure_liquidate_borrow_allowed` uses `get_price` (EMA) for eligibility, causing borrowers to lose excess collateral when spot and EMA prices diverge, as the liquidator can time liquidations to maximize the difference.

## Root Cause

In [`market.move:1045-1046`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L1045-L1046), the collateral seizure calculation uses **spot prices**:

```move
let price_borrowed = get_spot_price(x_oracle, debt_type, oracle_base_token, clock);
let price_collateral = get_spot_price(x_oracle, collateral_type, oracle_base_token, clock);
```

While in [`market.move:1115`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L1115) and [`market.move:1155`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L1155), the eligibility check uses **EMA prices** via `get_price`.

Critically, `liquidate_calculate_seize_ctokens` does **not** use `get_price_with_check` (which enforces EMA-spot divergence tolerance). The non-liquidation paths (`debts_value_usd_non_liquidation`, `collaterals_usd_non_liquidation`) use `get_price_with_check` with a configurable tolerance (default 10%), but the liquidation seizure path has **no** such guard.

## Internal Pre-conditions

1. An obligation needs to be in a liquidatable state (weighted_debts > collateral_weighted_value based on EMA prices).
2. EMA-spot price divergence for the debt or collateral token needs to be non-trivial (e.g., >1%).

## External Pre-conditions

1. Market volatility needs to cause the spot price to diverge from the EMA price for either the debt token or collateral token.

## Attack Path

1. Liquidator monitors obligations near the liquidation threshold.
2. Liquidator waits for a moment when the spot price of the debt token is **higher** than EMA (or collateral spot is **lower** than EMA).
3. Liquidator calls `liquidate()` at `liquidate.move:133`.
4. `ensure_liquidate_borrow_allowed` passes using EMA prices (obligation is liquidatable by EMA).
5. `liquidate_calculate_seize_ctokens` computes seizure using spot prices: `seized = repay_amount * (1 + incentive) * spot_debt_price / spot_collateral_price / exchange_rate`.
6. Because spot debt price > EMA debt price (or spot collateral price < EMA collateral price), the liquidator seizes **more** collateral than the EMA-based eligibility check would justify.
7. The borrower loses excess collateral proportional to the EMA-spot divergence.

## Impact

The borrower suffers excess collateral loss proportional to the EMA-spot price divergence. With the default EMA-spot tolerance of 10% (which is NOT enforced on the liquidation seizure path), a liquidator can extract up to ~10% more collateral than what the EMA-based health check would fairly warrant.

For example, on a $10,000 liquidation with a 10% EMA-spot divergence on the debt token, the liquidator seizes ~$1,000 of additional collateral beyond what the EMA valuation justifies. However, such extreme divergence is uncommon under normal market conditions; realistic excess extraction in typical volatility is in the 1-3% range.

**Severity: Medium** — Per [Sherlock judging guidelines](https://docs.sherlock.xyz/audits/judging/guidelines), this falls under *"Causes a loss of funds but requires certain external conditions or specific states."* Exploitation depends on organic EMA-spot divergence driven by market volatility (attacker cannot amplify the gap without separate oracle manipulation). Additionally, the borrower is already in a legitimately liquidatable state; the bug only causes *excess* seizure, not an illegitimate liquidation.

## PoC

Code path comparison:

1. **Eligibility** (`ensure_liquidate_borrow_allowed`):
   - `collaterals_usd_for_liquidation` (line 1086) calls `get_price` (EMA) at line 1115
   - `debts_value_usd_for_liquidation` (line 1129) calls `get_price` (EMA) at line 1155

2. **Seizure** (`liquidate_calculate_seize_ctokens`):
   - Line 1045: `get_spot_price(x_oracle, debt_type, ...)` -- raw spot, no divergence check
   - Line 1046: `get_spot_price(x_oracle, collateral_type, ...)` -- raw spot, no divergence check

3. **Non-liquidation** (borrow/withdraw safety checks):
   - `collaterals_usd_non_liquidation` (line 1252) uses `get_price_with_check` at line 1280 -- WITH divergence guard
   - `debts_value_usd_non_liquidation` (line 1170) uses `get_price_with_check` at line 1198 -- WITH divergence guard

The liquidation seizure path is the only critical path with no EMA-spot divergence protection.

## Mitigation

Either:
1. Use EMA prices (via `get_price`) for the seizure calculation as well, ensuring consistency with the eligibility check.
2. Use `get_price_with_check` in `liquidate_calculate_seize_ctokens` to enforce the EMA-spot tolerance and revert liquidations during extreme divergence periods.
3. Use the minimum of spot and EMA for the debt price and maximum for the collateral price in the seizure calculation, ensuring the calculation never exceeds the EMA-based valuation.
