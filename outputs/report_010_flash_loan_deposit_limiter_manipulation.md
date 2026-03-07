# Attacker will bypass withdrawal rate limiter by using flash loan deposit to reduce outflow counter

## Summary

`handle_mint` (deposit) calls `reduce_outflow` on the deposit limiter at `market.move:298`, and flash loans do not interact with the limiter at all, allowing a whitelisted caller to flash-loan tokens, deposit them to reduce the outflow counter, withdraw them, and repay — effectively resetting the rate limiter's protection within a single PTB.

## Root Cause

In [`market.move:298`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L298), a deposit reduces the outflow counter:

```move
emode.borrow_mut_deposit_limiter().reduce_outflow(now, deposit_amount);
```

In [`market.move:349-352`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L349-L352), a withdrawal adds to the outflow counter:

```move
emode.borrow_mut_deposit_limiter().add_outflow(now, deposit.value());
```

Flash loan borrow ([`market.move:795-818`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L795-L818)) and repay ([`market.move:820-856`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L820-L856)) never call `add_outflow` or `reduce_outflow`.

The `reduce_outflow` function in [`limiter.move:100-119`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/limiter.move#L100-L119) saturates at zero for the current segment:

```move
if (segment.value <= reduced_value) {
    segment.value = 0;
} else {
    segment.value = segment.value - reduced_value;
}
```

## Internal Pre-conditions

1. A `PackageCallerCap` with both flash loan permission (ID 0) and deposit/withdraw capabilities needs to exist (or the same entity controls caps with different permissions).
2. The deposit rate limiter's current segment needs to have accumulated outflow from prior withdrawals.

## External Pre-conditions

None.

## Attack Path

1. Over the past hours, legitimate withdrawals have consumed 800,000 of the 1,000,000 token outflow limit for the current cycle.
2. Attacker (whitelisted) wants to withdraw 500,000 more tokens, but only 200,000 of outflow capacity remains.
3. Attacker constructs a PTB:
   a. Flash loan 800,000 tokens.
   b. Deposit 800,000 tokens → `reduce_outflow(now, 800,000)` reduces the current segment's value by 800,000, effectively zeroing it.
   c. Withdraw 500,000 tokens → `add_outflow(now, 500,000)` adds 500,000 to the now-zeroed segment. Check passes: `0 + 500,000 <= 1,000,000`.
   d. Withdraw the deposited 800,000 tokens → `add_outflow(now, 800,000)`.
   e. Repay flash loan (800,000 + fee).
4. The attacker has withdrawn 500,000 tokens beyond the intended cycle limit.

**Note:** The effectiveness depends on how much outflow is in the current segment vs. previous segments. The `reduce_outflow` only affects the current segment (by design — see comment at `limiter.move:98-99`), so it can only zero the current segment's accumulated outflow. If most outflow accumulated in previous segments, the manipulation is less effective.

## Impact

The rate limiter can be partially bypassed by using flash loan deposits to reset the current segment's outflow counter. The attacker can withdraw more tokens per cycle than the admin-configured limit intends to allow, potentially draining liquidity faster than depositors can react.

The effectiveness is proportional to how much outflow was accumulated in the current segment (same time window as the attack). Cross-segment outflow from prior windows cannot be reduced.

## Mitigation

Either:
1. Do not call `reduce_outflow` on deposits. Instead, track deposits and withdrawals independently.
2. Add a flag to detect flash-loan-sourced deposits and exclude them from `reduce_outflow`.
3. Apply `add_outflow` to flash loan borrows as well, so flash-loaned tokens are rate-limited like regular borrows.
