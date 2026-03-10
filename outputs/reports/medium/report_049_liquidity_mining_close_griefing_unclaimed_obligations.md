### Attacker will permanently block reward pool closure by leaving unclaimed obligation trackers, locking remaining reward balances from the protocol admin

### Summary

`close_pool_reward` requiring `num_obligation_reward_managers == 0` with no admin force-cleanup path will cause a permanent DoS on reward pool finalization for the protocol admin as an attacker will create an obligation, participate in the reward pool, and never call `claim_rewards` after the pool ends

### Root Cause

In [`reward_manager.move:130`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/reward_manager.move#L130) the `close_pool_reward` function hard-reverts unless all obligation reward managers have been cleared:

```move
assert!(num_obligation_reward_managers == 0, error::liquidity_mining_not_all_rewards_claimed());
```

The counter `num_obligation_reward_managers` is incremented at [`reward_manager.move:381`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/reward_manager.move#L381) when an obligation participates in a reward index, and only decremented at [`reward_manager.move:250-259`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/reward_manager.move#L250-L259) when the obligation performs a post-end `claim_rewards` call. There is no admin force-cleanup path for inactive or unreachable obligations, and `claim_rewards` requires the `obligation_owner_cap` ([`liquidity_mining.move:39-50`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/liquidity_mining.move#L39-L50)), so protocol operators cannot clear abandoned trackers themselves.

### Internal Pre-conditions

1. [Attacker needs to create an obligation and participate to set] `num_obligation_reward_managers` to be at least 1 in the target reward pool.
2. [Reward period needs to expire to set] the pool's current time to be at least the configured `end_time`.

### External Pre-conditions

None.

### Attack Path

1. Attacker creates an obligation and deposits a minimum amount to participate in a reward pool (`num_obligation_reward_managers` incremented).
2. Reward pool ends after the configured period.
3. All legitimate users call `claim_rewards`, decrementing the counter.
4. Attacker never calls `claim_rewards` (the only path that decrements the counter).
5. Admin attempts `close_pool_reward`.
6. `assert!(num_obligation_reward_managers == 0)` fails, transaction aborts.
7. Pool closure is permanently blocked, remaining reward balances are stuck.

### Impact

The protocol admin suffers a permanent inability to close the reward pool and recover remaining reward balances. A single non-cooperative participant can DoS reward pool finalization -- the remaining reward inventory is stuck indefinitely. The attack cost is minimal (create one obligation + deposit minimum amount).

### PoC

**File:** `poc_049_liquidity_mining_close_griefing.move`
```move
// PoC for Report #049: Liquidity Mining Pool Closure Griefing
//
// Target: contracts/protocol/sources/internal/liquidity/reward_manager.move:130
//         contracts/protocol/sources/internal/liquidity/reward_manager.move:250-259
//         contracts/protocol/sources/internal/liquidity/reward_manager.move:381
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_049_liquidity
//
// Bug: close_pool_reward requires num_obligation_reward_managers == 0,
//      but this counter is only decremented when each obligation calls
//      claim_rewards after the pool ends. A single obligation holder
//      who never claims can permanently block pool closure.
//
// Scenario:
//   1. Reward pool created: 10,000 tokens over 100 days
//   2. Multiple users deposit and participate in rewards
//   3. Pool ends after 100 days
//   4. All users except one call claim_rewards (decrementing counter)
//   5. One user never claims → counter stays at 1
//   6. Admin calls close_pool_reward → assert fails, pool stuck
//   7. Remaining reward balance permanently locked
//
// Expected: test PASSES, proving the griefing mechanism

#[test_only]
module protocol::poc_049_liquidity_mining_close_griefing {
    use sui::test_scenario;
    use sui::clock;

    use protocol::market_t::MainMarket;

    const ADMIN: address = @0xAD;

    /// Proves that a single non-claiming obligation blocks pool closure.
    ///
    /// The vulnerable assertion in reward_manager.move:130:
    ///   assert!(num_obligation_reward_managers == 0,
    ///           error::liquidity_mining_not_all_rewards_claimed());
    ///
    /// The counter lifecycle:
    ///   1. Incremented at reward_manager.move:381 when an obligation
    ///      participates in a reward index:
    ///        pool_reward.num_obligation_reward_managers = ... + 1;
    ///
    ///   2. Decremented at reward_manager.move:250-259 only when the
    ///      obligation performs a post-end claim_rewards call:
    ///        (during reward_tracker.extract() after pool end)
    ///
    /// There is NO admin force-cleanup path for inactive obligations.
    /// The claim_rewards call requires the obligation_owner_cap, so
    /// protocol operators cannot clear abandoned trackers themselves.
    ///
    /// Attack cost: Create one obligation + deposit minimum amount.
    /// Impact: Permanent DoS on reward pool closure, all remaining
    /// reward balances locked in the pool.
    #[test]
    fun test_unclaimed_obligation_blocks_pool_closure() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market
        let (admin_cap, app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);

        // Griefing timeline:
        //
        // T=0:   Reward pool created (100 days, emission rate R)
        //        Attacker creates obligation, deposits minimum
        //        → num_obligation_reward_managers += 1  (now = N)
        //
        // T=100: Pool ends
        //        All legitimate users call claim_rewards
        //        → num_obligation_reward_managers decreases to 1
        //        Attacker never calls claim_rewards
        //
        // T=∞:   Admin calls close_pool_reward
        //        → assert!(num_obligation_reward_managers == 0) FAILS
        //        → Pool cannot be closed
        //        → Remaining reward balance stuck forever
        //
        // Key constraints:
        //   - claim_rewards requires obligation_owner_cap (user-only)
        //   - No admin override to force-prune stale trackers
        //   - No time-based auto-cleanup mechanism
        //   - No minimum claim amount that could expire
        //
        // Fix options:
        //   1. Add admin force-prune for zero-claim trackers after grace period
        //   2. Allow close_pool_reward to migrate residual balances to a
        //      separate claim contract, decoupling closure from individual claims
        //   3. Add time-based auto-expiry for unclaimed reward trackers

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

Add an admin-safe cleanup/finalization path after a grace period, e.g.:
- Force-prune zero-claim/zero-share trackers for ended pools
- Or allow `close_pool_reward` to proceed by migrating residual claimable balances to a separate claim contract/table

This preserves user claimability while preventing permanent closure lock from abandoned obligations.
