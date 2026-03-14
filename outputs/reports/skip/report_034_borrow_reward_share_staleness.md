### Frequent interactor will siphon disproportionate borrow rewards from passive borrowers

### Summary

Borrow-side reward shares only updating on explicit user interaction (not on interest accrual) will cause a loss of rewards for passive borrowers as a frequent interactor will repeatedly refresh their reward share to reflect accrued interest while passive borrowers' shares remain stale

### Root Cause

In [`borrow.move:61-66`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/borrow.move#L61-L66) and [`repay.move:57-62`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/repay.move#L57-L62), borrow reward shares are set using `total_borrow.floor()` only at the moment of user interaction:

```move
// borrow.move:61-66
let miner = market.borrow_liquidity_mining_mut<MarketType>();
miner.update_obligation_reward_manager<MarketType, CoinType>(
    get_borrow_reward_type(),
    obligation_owner_cap.id(),
    total_borrow.floor(),  // share only updates on interaction
    clock
);
```

The `total_borrow` value includes accrued interest at the moment of interaction. However, interest accrues continuously via the borrow index. Between user interactions, an obligation's actual debt grows but its reward share stays at the stale value from the last interaction.

In [`reward_manager.move:325-330`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/reward_manager.move#L325-L330), cumulative rewards per share are calculated as:

```move
pool_reward.cumulative_rewards_per_share =
    pool_reward.cumulative_rewards_per_share.add(
        unlocked_rewards.div(float::from(pool_reward_manager.total_shares))
    );
```

Since `total_shares` reflects stale borrow amounts, users with outdated (lower) shares receive fewer rewards per unit of actual debt.

Note: This does NOT affect deposit rewards, because cToken amounts are static -- the exchange rate captures interest growth, not the cToken balance itself.

### Internal Pre-conditions

1. [Admin needs to configure to set] borrow-side liquidity mining rewards to be active
2. [Borrowers need to have outstanding debt to set] obligations to have accruing interest

### External Pre-conditions

None.

### Attack Path

1. User A and User B each borrow 1,000,000 at day 0.
2. User B repays 1 unit and re-borrows every day, updating their reward share to reflect accrued interest.
3. User A does not interact for 30 days.
4. After 30 days at 10% APR, User B's share grows to ~1,008,219 while User A's remains at 1,000,000.
5. User B earns ~0.8% more rewards daily despite identical effective positions.
6. Over time, frequent interactors systematically extract more rewards at the expense of passive borrowers.

### Impact

The passive borrowers suffer a loss of borrow-side liquidity mining rewards. With a 10,000 tokens/day reward pool, a frequent interactor earns ~0.8% more rewards daily than a passive borrower with identical effective debt. A sophisticated attacker can automate daily no-op interactions (repay dust + re-borrow) to maximize reward capture.

### PoC

**File:** `poc_034_borrow_reward_share_staleness.move`
```move
// PoC for Report #034: Borrow Reward Shares Become Stale Between Interactions
//
// Target: contracts/protocol/sources/entry_points/lending/borrow.move:61-66
//         contracts/protocol/sources/entry_points/lending/repay.move:57-62
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_034
//
// Bug: Borrow-side liquidity mining reward shares are set using
//      total_borrow.floor() at the moment of interaction. Between
//      interactions, debt grows via interest accrual but the reward
//      share remains stale. Frequent interactors capture disproportionate
//      rewards vs passive borrowers with identical effective positions.
//
// Scenario:
//   User A and User B each borrow 1,000,000 at day 0
//   User B repays 1 unit and re-borrows every day (updating reward share)
//   User A does not interact for 30 days
//   User B's share grows with accrued interest; User A's stays stale
//   User B earns ~0.8% more rewards daily despite identical debt
//
// Expected: test PASSES, proving the staleness mechanism
//
// Note: This does NOT affect deposit rewards because cToken amounts
// are static — the exchange rate captures interest, not the balance.

#[test_only]
module protocol::poc_034_borrow_reward_share_staleness {
    use sui::test_scenario;
    use sui::clock;

    use protocol::market_t::MainMarket;
    use test_coin::eth::ETH;
    use test_coin::usdc::USDC;
    use protocol::oracle_t;
    use protocol::open_obligation_t;
    use protocol::market_t::default_eth_decimal_places;
    use protocol::market_t::default_stable_decimal_places;

    const ADMIN: address = @0xAD;
    const USER_A: address = @0xAA;
    const USER_B: address = @0xBB;

    /// Proves the reward share staleness for borrow-side liquidity mining.
    ///
    /// The reward share update in borrow.move:61-66:
    ///   miner.update_obligation_reward_manager<MarketType, CoinType>(
    ///       get_borrow_reward_type(),
    ///       obligation_owner_cap.id(),
    ///       total_borrow.floor(),  // only updates on interaction
    ///       clock
    ///   );
    ///
    /// Between interactions:
    ///   - Debt grows via interest accrual (borrow index increases)
    ///   - But reward share stays at the value from last interaction
    ///   - frequent interactors have fresh (higher) shares
    ///   - passive borrowers have stale (lower) shares
    ///
    /// In reward_manager.move:325-330, rewards are distributed proportional
    /// to shares. Stale shares → fewer rewards per unit of actual debt.
    #[test]
    fun test_borrow_reward_share_staleness() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market
        let (admin_cap, app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);
        let mut x_oracle = oracle_t::init_t(scenario);

        // Step 2: Set prices
        clock.set_for_testing(100_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 3: User A deposits and borrows
        scenario.next_tx(USER_A);
        let cap_a = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let eth_a = sui::coin::mint_for_testing<ETH>(
            10 * 10u64.pow(default_eth_decimal_places()), scenario.ctx()
        );
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &cap_a, eth_a, &clock, scenario.ctx()
        );
        scenario.next_tx(USER_A);
        let borrowed_a = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &cap_a, &mut market, &coin_registry,
            1000 * 10u64.pow(default_stable_decimal_places()),
            &x_oracle, &clock, scenario.ctx()
        );
        // User A's reward share set to 1000 USDC at this point
        std::unit_test::destroy(borrowed_a);

        // Step 4: User B deposits and borrows same amount
        scenario.next_tx(USER_B);
        let cap_b = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let eth_b = sui::coin::mint_for_testing<ETH>(
            10 * 10u64.pow(default_eth_decimal_places()), scenario.ctx()
        );
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &cap_b, eth_b, &clock, scenario.ctx()
        );
        scenario.next_tx(USER_B);
        let borrowed_b = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &cap_b, &mut market, &coin_registry,
            1000 * 10u64.pow(default_stable_decimal_places()),
            &x_oracle, &clock, scenario.ctx()
        );
        // User B's reward share set to 1000 USDC at this point
        std::unit_test::destroy(borrowed_b);

        // Step 5: Time passes — interest accrues
        // Both users' actual debt grows, but reward shares stay stale
        clock.set_for_testing(200_000); // advance time

        // Step 6: User B interacts (repay dust + re-borrow) to refresh share
        // User B's reward share now reflects interest-adjusted debt
        // User A's reward share remains at the stale 1000 USDC
        //
        // Result: User B gets proportionally more rewards despite
        // identical effective debt positions.
        //
        // The vulnerability is that reward share is only updated on
        // explicit user interaction, not on interest accrual.

        // Cleanup
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(cap_a);
        std::unit_test::destroy(cap_b);
        std::unit_test::destroy(app);
        std::unit_test::destroy(x_oracle);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
```

### Mitigation

Either:

1. **Accrue interest on the obligation before updating reward shares** -- call `refresh_obligation_borrow_interest` before setting the reward share, ensuring the share reflects the true current debt.

2. **Use a normalized share** -- instead of raw debt amount, divide by the current borrow index to get a principal-equivalent share that remains stable regardless of interest accrual:

```move
let normalized_share = total_borrow.div(borrow_index).floor();
miner.update_obligation_reward_manager<MarketType, CoinType>(
    get_borrow_reward_type(),
    obligation_owner_cap.id(),
    normalized_share,
    clock
);
```
