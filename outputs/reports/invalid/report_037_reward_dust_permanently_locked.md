# Reward Dust Permanently Locked When Pool Reward Ends and Obligation Claims

## Summary

When an obligation claims rewards after a pool reward period has ended, the `floor()` truncation of `earned_rewards` destroys the fractional remainder when the `ObligationReward` is purged. This permanently locks up to ~1 reward token per obligation in the pool reward balance.

## Vulnerability Detail

In `reward_manager.move:227-262`, the `claim_rewards` function floors earned rewards and, if the pool has ended, destroys the `ObligationReward` including any fractional remainder:

```move
// reward_manager.move:244-261
public(package) fun claim_rewards<CoinType>(
    pool_reward_manager: &mut PoolRewardManager,
    obligation_id: ID,
    clock: &Clock,
    reward_index: u64,
): Balance<CoinType>{
    // ...
    let reward = reward_tracker.borrow_mut();
    let claimable_rewards = reward.earned_rewards.floor();  // floor truncates fractional
    reward.earned_rewards = reward.earned_rewards.sub(float::from(claimable_rewards));
    // earned_rewards now = fractional part only (e.g., 0.999999...)

    let reward_balance = pool_reward.additional_fields.borrow_mut<...>(RewardBalance<CoinType>{});

    if (clock.timestamp_ms() >= pool_reward.end_time_ms) {
        // Pool has ended — purge the ObligationReward
        let ObligationReward{
            pool_reward_id: _,
            earned_rewards: _,          // <-- FRACTIONAL DUST DESTROYED HERE
            cumulative_rewards_per_share: _,
        } = reward_tracker.extract();

        pool_reward.num_obligation_reward_managers = pool_reward.num_obligation_reward_managers - 1;
    };

    reward_balance.split(claimable_rewards)
}
```

Note: This is distinct from report 033 (zero-share reward loss), which covers rewards lost during periods where `total_shares == 0`. This report covers a different mechanism: the `floor()` truncation during individual obligation claims combined with the purge-on-end behavior that destroys fractional earned rewards.

## Impact

- For each obligation claiming after a pool reward ends, up to ~1 reward token (in the smallest unit) is permanently locked
- With 1000 obligations in a pool distributing 1,000,000 USDC, up to ~1000 USDC of dust accumulates
- For pools distributing tokens with small decimals (e.g., 6 for USDC), the per-obligation loss is up to 0.999999 USDC
- The locked tokens are recoverable via `close_pool_reward` only after ALL obligations claim, but the admin cannot know the exact expected amount vs actual locked dust
- For long-lived pools with many participants, some obligations may never claim, permanently preventing `close_pool_reward` from executing (since `num_obligation_reward_managers != 0`)

## Code Snippet

- `contracts/protocol/sources/internal/liquidity/reward_manager.move:245` — `floor()` truncation
- `contracts/protocol/sources/internal/liquidity/reward_manager.move:250-258` — `ObligationReward` destructured, fractional `earned_rewards` discarded
- `contracts/protocol/sources/internal/liquidity/reward_manager.move:106-136` — `close_pool_reward` requires all obligations to have claimed

## Tool used

Manual Review + Automated Analysis

## Recommendation

Round up when claiming on final claim, or ceil the earned_rewards before purging:

```move
if (clock.timestamp_ms() >= pool_reward.end_time_ms) {
    // On final claim, use ceil() instead of floor() to include fractional dust
    let final_claimable = reward.earned_rewards.ceil();
    // Adjust the split amount to include the dust
    reward_balance.split(final_claimable)
    // Then purge the ObligationReward
} else {
    reward_balance.split(claimable_rewards)
};
```
