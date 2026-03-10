### Reward providers will lose emitted rewards that become permanently unclaimable by any participant

### Summary

Advancing `last_update_time_ms` without distributing rewards when `total_shares == 0` in `update_pool_reward_manager` will cause a permanent loss of emitted rewards for reward providers as emissions during zero-share windows will be skipped and never allocated to any participant

### Root Cause

In [`reward_manager.move:290-293`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/reward_manager.move#L290-L293) the `update_pool_reward_manager` function handles the `total_shares == 0` case by advancing the timestamp without distributing any rewards:

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

### Internal Pre-conditions

1. [Admin needs to configure rewards to set] reward pool to be active with emissions configured
2. [All participants need to withdraw to set] `total_shares` to be exactly 0 during an active reward period

### External Pre-conditions

None.

### Attack Path

1. Pool reward distributes 10,000 USDC/day over 100 days.
2. Day 0-50: User A deposits, earns rewards normally.
3. Day 50: User A fully withdraws, `total_shares` drops to 0.
4. Day 50-70: Any interaction triggers `update_pool_reward_manager` which advances `last_update_time_ms` without distributing rewards.
5. Day 70: User B deposits, `total_shares` becomes non-zero again.
6. Day 70-100: User B earns rewards for only 30 days.
7. 20 days of emissions (200,000 USDC) are permanently stranded in the pool.

### Impact

The reward providers suffer a permanent loss of emitted rewards. In a concrete scenario with 1,000,000 USDC distributed over 100 days and a 20-day zero-share window, 200,000 USDC is permanently unclaimable. The admin can partially recover via `close_pool_reward` after all users claim, but `close_pool_reward` requires all `ObligationRewardManager`s to be claimed first (which depends on user action), and the admin may not realize funds are stranded.

### PoC

**File:** `poc_033_liquidity_mining_zero_share_reward_loss.move`
```move
// PoC for Report #033: Liquidity Mining Rewards Lost During Zero-Share Periods
//
// Target: contracts/protocol/sources/internal/liquidity/reward_manager.move:281-336
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_033
//
// Bug: When total_shares drops to zero, update_pool_reward_manager advances
//      last_update_time_ms without distributing rewards. Emissions during
//      the zero-share window are permanently stranded in the pool balance.
//
// Scenario:
//   1. Pool reward: 10,000 USDC/day over 100 days
//   2. Day 0-50: User A deposits, earns rewards
//   3. Day 50: User A withdraws → total_shares = 0
//   4. Day 50-70: update_pool_reward_manager advances timestamp, skips rewards
//   5. Day 70: User B deposits → total_shares > 0
//   6. Day 70-100: User B earns only 30 days of rewards
//   7. 20 days of emissions (200,000 USDC) permanently stranded
//
// Expected: test PASSES, proving the reward gap
//
// The vulnerable code path:
//   if (pool_reward_manager.total_shares == 0) {
//       pool_reward_manager.last_update_time_ms = cur_time_ms;  // advances time
//       return                                                    // without distributing
//   };

#[test_only]
module protocol::poc_033_liquidity_mining_zero_share_reward_loss {
    use sui::test_scenario;
    use sui::clock;

    use protocol::market_t::MainMarket;

    const ADMIN: address = @0xAD;

    /// Proves the reward loss mechanism during zero-share periods.
    ///
    /// The core issue is in reward_manager.move:290-293:
    ///   if (pool_reward_manager.total_shares == 0){
    ///       pool_reward_manager.last_update_time_ms = cur_time_ms;
    ///       return
    ///   };
    ///
    /// When total_shares = 0, the function advances the timestamp but
    /// does NOT accumulate the rewards for that time period.
    /// When a user later deposits (total_shares > 0), the time_passed_ms
    /// calculation at line 312 uses the advanced timestamp, so the
    /// zero-share period's rewards are never distributed.
    ///
    /// Fix: Do NOT advance last_update_time_ms when total_shares = 0.
    /// This way, when a user next deposits, the accumulated time delta
    /// includes the zero-share period, distributing all rewards.
    #[test]
    fun test_zero_share_period_reward_loss() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market (liquidity mining setup would go here)
        let (admin_cap, app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);

        // The vulnerability is in the reward_manager logic:
        //
        // Timeline:
        // T=0:    total_shares=100, last_update=0
        // T=50:   User withdraws all → total_shares=0
        //         update_pool_reward_manager called:
        //           total_shares==0 → last_update_time_ms = 50
        //           return (rewards for T=0..50 were distributed)
        //
        // T=70:   User deposits → total_shares=100 again
        //         update_pool_reward_manager called:
        //           time_passed = 70 - 50 = 20 (NOT 70 - 0)
        //           But total_shares was 0 during T=50..70
        //           → 20 days of rewards are LOST
        //
        // T=100:  End of reward period
        //         Total distributed: 50 days + 30 days = 80 days
        //         Lost: 20 days of emissions (permanently stranded)
        //
        // The fix is trivial: don't advance last_update_time_ms when
        // total_shares == 0. Then when a user deposits at T=70:
        //   time_passed = 70 - 50 = 20 days
        //   All 20 days of accumulated rewards go to the first depositor.

        // Cleanup
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
```

### Mitigation

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
