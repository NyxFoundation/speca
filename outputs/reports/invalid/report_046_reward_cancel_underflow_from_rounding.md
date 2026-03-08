# `cancel_pool_reward` Aborts When Accumulated Rounding Causes `allocated_rewards` to Exceed `total_rewards`

## Summary

`cancel_pool_reward` computes `unallocated_rewards = float::from(total_rewards).sub(allocated_rewards)`. Due to repeated fixed-point rounding in `update_pool_reward_manager`, `allocated_rewards` can marginally exceed `float::from(total_rewards)`, causing `float::sub` to abort on underflow. This permanently prevents the admin from cancelling the reward period, locking the unallocated funds.

## Root Cause

In [`reward_manager.move:148-151`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/liquidity/reward_manager.move#L148-L151):

```move
let unallocated_rewards =
    float::from(pool_reward.total_rewards).sub(
    pool_reward.allocated_rewards
    ).floor();
```

`float::sub` (in `float.move:44-48`) performs `a.value - b.value` without overflow/underflow protection:

```move
public fun sub(a: Decimal, b: Decimal): Decimal {
    Decimal { value: a.value - b.value }
}
```

In Move, `u256` subtraction aborts on underflow. If `allocated_rewards.value > float::from(total_rewards).value`, the transaction aborts.

The `allocated_rewards` field is incrementally updated in `update_pool_reward_manager` ([`reward_manager.move:316-320`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/liquidity/reward_manager.move#L316-L320)):

```move
let unlocked_rewards =
    float::from(pool_reward.total_rewards).mul(
        float::from(time_passed_ms)
    ).div(
    float::from(pool_reward.end_time_ms - pool_reward.start_time_ms)
    );

pool_reward.allocated_rewards = pool_reward.allocated_rewards.add(unlocked_rewards);
```

Each call independently computes `total_rewards * time_passed / total_duration` using 18-decimal fixed-point arithmetic. The multiplication `total_rewards * time_passed` may round up by up to 1 ULP (unit of least precision), and the subsequent division may round up again. Over many small time increments, these rounding errors accumulate. The sum of all `unlocked_rewards` can exceed `float::from(total_rewards)` by a small amount.

## Internal Pre-conditions

1. A pool reward must be active with non-zero `total_rewards`.
2. `update_pool_reward_manager` must be called many times with small time increments (this happens naturally as users stake/unstake, triggering updates on each interaction).
3. The reward period must be long enough relative to interaction frequency for rounding errors to accumulate past the threshold.

## External Pre-conditions

None. This is a pure arithmetic issue in the fixed-point math accumulation.

## Attack Path

1. Admin creates a pool reward with `total_rewards = 1,000,000` and a 30-day duration.
2. Over 30 days, users interact frequently (stake, unstake, claim). Each interaction calls `update_pool_reward_manager`, incrementally computing and adding `unlocked_rewards`.
3. After many small time increments, `allocated_rewards` accumulates to `1,000,000.000000000000000002` (tiny rounding overshoot).
4. Admin calls `cancel_pool_reward` to recover unallocated rewards.
5. `float::from(1_000_000).sub(allocated_rewards)` computes `1000000 * 10^18 - (1000000 * 10^18 + 2)`, which underflows.
6. Transaction aborts. Admin cannot cancel the reward period.
7. The remaining reward balance is locked in the pool. It can only be recovered via `close_pool_reward`, which requires ALL obligation reward managers to have claimed first (line 130: `assert!(num_obligation_reward_managers == 0)`).

## Impact

Admin loses the ability to cancel reward periods that have experienced heavy interaction. The unallocated reward funds become effectively locked until every single user has claimed their rewards and removed their obligation_reward_manager, which may never happen if users abandon positions.

## PoC

Code inspection confirms the vulnerability:

1. `cancel_pool_reward` (`reward_manager.move:148-151`): uses `float::sub` which aborts on underflow.
2. `float::sub` (`float.move:44-48`): `a.value - b.value` with no underflow guard.
3. `update_pool_reward_manager` (`reward_manager.move:316-320`): incrementally adds `unlocked_rewards` computed via independent fixed-point multiplication and division.
4. Each `unlocked_rewards` computation: `float::from(total) * float::from(time_passed) / float::from(total_time)` — multiplication rounds up by up to 1 ULP, division may round up again.
5. Sum of rounded intermediates can exceed `float::from(total_rewards)`.

Compare with the `saturating_sub` function available in `float.move:55-61` — using this instead of `sub` would gracefully handle the overflow, returning zero instead of aborting.

## Mitigation

Replace `float::sub` with `float::saturating_sub` in the `cancel_pool_reward` function:

```move
let unallocated_rewards =
    float::from(pool_reward.total_rewards).saturating_sub(
    pool_reward.allocated_rewards
    ).floor();
```

This ensures that if rounding causes `allocated_rewards` to slightly exceed `total_rewards`, the result is clamped to zero rather than aborting.
