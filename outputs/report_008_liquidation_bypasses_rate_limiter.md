# Whitelisted liquidator will drain reserve beyond rate limit by exploiting limiter bypass in liquidation path

## Summary

`liquidation_inner` explicitly disables the rate limiter (`// NOTE: disable rate limit` at `market.move:745`), allowing whitelisted liquidators to extract unlimited collateral from a reserve within a single rate-limiting cycle, defeating the purpose of the outflow limiter designed to prevent rapid reserve draining.

## Root Cause

In [`market.move:745`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L745), the rate limiter is explicitly disabled for the liquidation path:

```move
// NOTE: disable rate limit
```

Compare with the withdraw path at [`market.move:349-352`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L349-L352) which correctly enforces the limiter:

```move
let now = clock.timestamp_ms() / 1000;
let emode = self.emode_group_registry.borrow_emode_group_mut(obligation.emode_group());
emode.borrow_mut_deposit_limiter().add_outflow(now, deposit.value());
```

And the borrow path at [`market.move:402`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L402):

```move
emode.borrow_mut_borrow_limiter().add_outflow(now, borrow_amount);
```

The `liquidation_inner` function (lines 691-793) is shared by normal liquidation (`handle_liquidation`), ADL borrow (`handle_debt_auto_deleverage`), and ADL collateral (`handle_collateral_auto_deleverage`). None of these paths call `add_outflow` on the deposit limiter for the seized collateral.

## Internal Pre-conditions

1. A `PackageCallerCap` with liquidation permission needs to exist (whitelisted liquidator).
2. One or more obligations need to be in a liquidatable state.

## External Pre-conditions

1. Market volatility needs to create liquidatable positions (or the whitelisted liquidator contract is compromised/malicious).

## Attack Path

1. Market downturn makes multiple obligations liquidatable simultaneously.
2. A compromised or malicious whitelisted liquidator calls `liquidate()` repeatedly against multiple obligations.
3. Each liquidation seizes collateral from the reserve without any rate limiter check.
4. In a single rate-limiting cycle (e.g., 24 hours), the liquidator can drain the entire collateral reserve — far exceeding the `outflow_limit` set by the admin.
5. Legitimate depositors attempting to withdraw find insufficient liquidity, as the rate limiter only protects the withdraw and borrow paths, not the liquidation path.

## Impact

The rate limiter's core security guarantee — preventing rapid reserve draining — is voided for the highest-value outflow path. During a market crash (precisely when the rate limiter is most needed), mass liquidations can drain a reserve far beyond the admin-configured outflow limit. This leaves depositors unable to withdraw their funds even though the limiter was intended to protect them.

The impact is amplified because liquidation is the primary mechanism through which large amounts of collateral are extracted during market stress events.

## Mitigation

Either:
1. Add `add_outflow` calls in `liquidation_inner` for the seized collateral amount, consistent with the withdraw path.
2. Create a separate, higher outflow limit specifically for liquidations that is still bounded, rather than disabling the limiter entirely.
3. If the design intent is to never rate-limit liquidations (to ensure protocol solvency), document this explicitly and ensure depositors understand the rate limiter does not protect against liquidation-driven outflows.
