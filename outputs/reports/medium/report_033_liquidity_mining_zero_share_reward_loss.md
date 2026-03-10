# Liquidity Mining Rewards Permanently Lost During Zero-Share Periods

## Summary

When all users withdraw from a reward pool (`total_shares` drops to zero), `update_pool_reward_manager` advances `last_update_time_ms` without distributing any rewards. Emissions during this zero-share window are permanently stranded in the pool balance.

## Vulnerability Detail

In `reward_manager.move:281-336`, the `update_pool_reward_manager` function handles the `total_shares == 0` case by simply advancing the timestamp:

```move
fun update_pool_reward_manager(
    pool_reward_manager: &mut PoolRewardManager,
    clock: &Clock
){
    let cur_time_ms = clock.timestamp_ms();
    if(cur_time_ms == pool_reward_manager.last_update_time_ms){
        return
    };

    if (pool_reward_manager.total_shares == 0){
        pool_reward_manager.last_update_time_ms = cur_time_ms;  // advances time
        return                                                    // without distributing rewards
    };

    // ... reward allocation logic (only reached when total_shares > 0) ...
}
```

The reward distribution (lines 295-332) calculates `time_passed_ms` based on `last_update_time_ms` and `cur_time_ms`. Since `last_update_time_ms` was already advanced during the zero-share period, the rewards for that period are never calculated or allocated.

## Internal Pre-conditions

1. Reward pool must be active with emissions configured.
2. All participants must have withdrawn (`total_shares` = 0) during an active reward period.

## External Pre-conditions

None.

## Attack Path

1. Pool reward distributes 10,000 USDC/day over 100 days.
2. Day 0-50: User A deposits, earns rewards.
3. Day 50: User A fully withdraws, `total_shares` drops to 0.
4. Day 50-70: `update_pool_reward_manager` advances `last_update_time_ms` without distributing rewards.
5. Day 70: User B deposits.
6. Day 70-100: User B earns rewards for only 30 days.
7. 20 days of emissions (200,000 USDC) are stranded in the pool.

## Impact

Consider a concrete scenario:
1. Pool reward: 1,000,000 USDC distributed over 100 days (10,000 USDC/day)
2. Day 0-50: User A has 100% share, earns 500,000 USDC
3. Day 50: User A fully withdraws (total_shares = 0)
4. Day 70: User B deposits (total_shares > 0 again)
5. Day 70-100: User B earns 300,000 USDC (30 days of rewards)
6. Result: **200,000 USDC** (days 50-70) is permanently unclaimable

The admin can partially recover via `close_pool_reward` after all users claim, but:
- Admin may not realize funds are stranded
- `close_pool_reward` requires all `ObligationRewardManager`s to be claimed first, which depends on user action
- The stranded amount can be significant for volatile markets with periodic zero-participation windows

## Code Snippet

- `reward_manager.move:290-293` — Zero-share early return advancing timestamp
- `reward_manager.move:312-314` — `time_passed_ms` calculation that skips the zero-share period
- `reward_manager.move:316-323` — Reward distribution logic (never reached for zero-share window)

## Tool used

Manual Review + Automated Analysis

## Mitigation

Accumulate undistributed rewards instead of skipping them. When `total_shares` returns to non-zero, distribute the accumulated gap rewards to the first participants:

```move
if (pool_reward_manager.total_shares == 0){
    // Do NOT advance last_update_time_ms.
    // When a user next joins, the full time delta will be used,
    // distributing accumulated rewards to the first participant(s).
    return
};
```

Alternatively, track a separate `undistributed_rewards` counter and add it to the next distribution cycle.
