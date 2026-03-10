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
