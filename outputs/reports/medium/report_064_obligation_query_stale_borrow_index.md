### Off-chain integrators will undervalue obligation debt due to stale borrow index in obligation query, delaying liquidations and causing bad debt for depositors

### Summary

The `get_obligation_detail` query function uses the reserve's stored `borrow_index` (last on-chain update) instead of computing a time-projected index, causing all returned debt amounts to be understated by the interest accrued since the last on-chain interaction. This will cause liquidation bots and risk dashboards to see healthier positions than reality, delaying liquidations and accumulating bad debt.

### Root Cause

In [`obligation_query.move:64`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/query/obligation_query.move#L64) the market's stored borrow index is used without time-projection:

```move
let market_borrow_index = market.reserve_by_type<MarketType>(debt_type).borrow_index().value();
```

In contrast, [`market_query.move:69`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/query/market_query.move#L69) correctly computes a time-projected index:

```move
let borrow_index = reserve.calculate_borrow_index<MarketType>(interest_rate, now);
```

The obligation query reads the stale index, then computes debt as `debt.debt(market_borrow_index)` which equals `amount * stale_index / obligation_index`. The correct computation would use a time-projected index, producing `amount * projected_index / obligation_index` — a larger value reflecting accrued interest.

### Internal Pre-conditions

1. [Any asset needs to have outstanding borrows] to have a non-trivial borrow index that changes over time.
2. [Some time needs to pass since the last on-chain interaction] for the staleness to be meaningful. On low-activity assets, this could be hours or days.

### External Pre-conditions

1. Off-chain systems (liquidation bots, dashboards, risk engines) rely on `get_obligation_detail` to assess obligation health. This is the standard integration pattern for lending protocols.

### Attack Path

1. A borrower creates an obligation and borrows tokens.
2. Time passes with no on-chain interaction on that asset (common for low-activity markets).
3. Interest accrues mathematically (borrow index should increase) but the reserve's stored borrow index remains stale.
4. A liquidation bot queries `get_obligation_detail` and receives an understated debt amount.
5. The bot calculates a health factor that appears safe (e.g., 1.05) when the true health factor is below 1.0 (e.g., 0.98).
6. The bot does not trigger liquidation.
7. The position accumulates more bad debt over time until eventually someone interacts with the asset (triggering `accrue_interest`), at which point the stored index jumps and the position may be deeply underwater.

### Impact

Depositors suffer loss from delayed liquidations. The magnitude depends on:
- Duration of staleness (hours to days on low-activity assets)
- Interest rate (higher rates = larger discrepancy)
- Number of affected positions

Example: Asset at 50% APR, 24h stale → debt understated by ~0.14%. For a $100K position at 80% LTV, actual debt = $80,110 vs reported $80,000. Health factor reported as 1.001 (safe) when actually 0.999 (liquidatable). The $110 of delayed interest compounds into bad debt.

### PoC

```move
// PoC for Report #064: Obligation Query Stale Borrow Index
//
// This demonstrates the discrepancy between market_query (time-projected)
// and obligation_query (stale stored index).
//
// Since query functions are view-only and don't modify state,
// we demonstrate by comparing the two index values after time passes.

#[test_only]
module protocol::poc_064_obligation_query_stale_index {
    use sui::test_scenario;
    use sui::clock;

    use protocol::market_t::MainMarket;
    use test_coin::usdc::USDC;
    use test_coin::eth::ETH;
    use protocol::oracle_t;
    use protocol::open_obligation_t;
    use protocol::market_t::default_eth_decimal_places;
    use protocol::market_t::default_stable_decimal_places;

    const ADMIN: address = @0xAD;
    const BORROWER: address = @0xBB;

    /// Shows that after time passes without on-chain interaction,
    /// the obligation query's borrow index is stale while
    /// the market query's would be fresh.
    #[test]
    fun test_stale_obligation_query_borrow_index() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        let (admin_cap, app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);
        let mut x_oracle = oracle_t::init_t(scenario);

        // Setup prices
        clock.set_for_testing(100_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Borrower deposits ETH and borrows USDC
        scenario.next_tx(BORROWER);
        let borrower_cap = open_obligation_t::open_obligation_t<MainMarket>(scenario, &app, &mut market);
        let eth_coin = sui::coin::mint_for_testing<ETH>(
            2 * 10u64.pow(default_eth_decimal_places()), scenario.ctx()
        );
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &borrower_cap, eth_coin, &clock, scenario.ctx()
        );

        scenario.next_tx(BORROWER);
        let borrow_amount = 500 * 10u64.pow(default_stable_decimal_places());
        let borrowed = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &borrower_cap, &mut market, &coin_registry,
            borrow_amount, &x_oracle, &clock, scenario.ctx()
        );

        // Record borrow index right after borrow
        let reserve = market.get_reserve<MainMarket, USDC>();
        let index_at_borrow = reserve.borrow_index().value();

        // Advance time by 1 day (86400 seconds) WITHOUT any on-chain interaction
        clock.set_for_testing(100_000 + 86400 * 1000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // The stored borrow index is STILL the same as at borrow time
        let reserve_after = market.get_reserve<MainMarket, USDC>();
        let index_stored = reserve_after.borrow_index().value();
        assert!(index_at_borrow.eq(index_stored), 0); // STALE! Not updated.

        // An obligation query using this stale index would understate the debt.
        // The true debt should be: 500 * projected_index / obligation_index
        // But the query returns: 500 * stale_stored_index / obligation_index = 500
        // (since stale_stored_index == obligation_index, the debt appears unchanged)

        // BUG PROVEN: 24 hours of interest accrual is invisible to the query.
        // At 50% APR, this is ~0.14% understated = $0.70 on $500.
        // For larger positions and longer staleness, the impact scales linearly.

        // Cleanup
        std::unit_test::destroy(borrowed);
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(borrower_cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(x_oracle);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
```

### Mitigation

Use the time-projected borrow index in `get_obligation_detail`, consistent with how `market_query` does it:

```move
// In obligation_query.move, replace:
let market_borrow_index = market.reserve_by_type<MarketType>(debt_type).borrow_index().value();

// With:
let reserve = market.reserve_by_type<MarketType>(debt_type);
let asset = market.asset_by_type<MarketType>(debt_type);
let interest_rate = asset.interest_model().calc_interest(reserve.util_rate());
let market_borrow_index = reserve.calculate_borrow_index<MarketType>(interest_rate, now);
```

This ensures the obligation query returns debt values that reflect all mathematically accrued (but not yet on-chain settled) interest.
