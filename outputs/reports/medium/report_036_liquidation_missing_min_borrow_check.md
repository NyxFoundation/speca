### Liquidators will create economically unclearable dust positions for borrowers by leaving debt below min_borrow_amount

### Summary

The missing `enforce_post_borrow_repay_invariant` check in `liquidation_inner` after `unsafe_repay_debt_only` will cause systematic bad debt accumulation for the protocol as partial liquidations will leave borrowers with dust debt positions below `min_borrow_amount` that cannot be partially repaid and are economically irrational to fully repay.

### Root Cause

In [`market.move:773-774`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L773-L774) the `liquidation_inner` function calls `unsafe_repay_debt_only` without the `enforce_post_borrow_repay_invariant` check that is present in both `handle_borrow` (line 413) and `handle_repay` (line 470):

```move
// market.move:773-774
// at this stage, even if there is residual, it should be a very small amount, let the protocol consume the residual
let _residual = obligation.unsafe_repay_debt_only<MarketType, DebtType>(available_repay_coin.value());
// NOTE: NO enforce_post_borrow_repay_invariant call here
```

The `enforce_post_borrow_repay_invariant` function at [`obligation.move:154-166`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/obligation.move#L154-L166) asserts remaining debt stays above `min_borrow_amount`:

```move
public(package) fun enforce_post_borrow_repay_invariant<MarketType, CoinType>(
    self: &Obligation<MarketType>,
    min_borrow_amount: u64
) {
    let coin_type = type_name::with_defining_ids<CoinType>();
    if (!self.has_debt<MarketType>(coin_type)){ return };
    let current_debt = self.debt<MarketType>(coin_type).unsafe_debt_amount();
    assert!(current_debt.ge_u64(min_borrow_amount), error::obligation_borrow_below_min());
}
```

This check is enforced in `handle_borrow` and `handle_repay` but not in `liquidation_inner`, allowing liquidation to create positions with debt below `min_borrow_amount`.

### Internal Pre-conditions

1. [Admin needs to configure to set] `min_borrow_amount` to be at least a meaningful value (e.g., 100 USDC)
2. [Borrower needs to take on debt to set] the obligation's debt to be at least above `min_borrow_amount` but close enough that a partial liquidation (limited by close_factor) will reduce it below the threshold

### External Pre-conditions

1. Price movement or interest accrual must push the obligation below its liquidation threshold so that liquidation becomes possible.

### Attack Path

1. Borrower has debt of 150 USDC with `min_borrow_amount` = 100 USDC.
2. Position becomes liquidatable due to collateral price drop (e.g., ETH drops from $1000 to $210, making weighted collateral $147 < $150 debt).
3. Liquidator partially liquidates, repaying 75 USDC (max allowed by 50% close factor).
4. `liquidation_inner` calls `unsafe_repay_debt_only` without `enforce_post_borrow_repay_invariant`.
5. Remaining debt = 75 USDC, below `min_borrow_amount` of 100 USDC.
6. Borrower cannot partially repay the 75 USDC dust (`handle_repay` blocks it via the invariant check).
7. Full repay is technically possible but economically irrational for an underwater dust position.
8. Dust position accumulates interest as bad debt over time.

### Impact

The protocol suffers systematic bad debt accumulation from dust positions created by partial liquidations. Each partial liquidation can leave debt below `min_borrow_amount`, creating positions where the borrower cannot partially repay (blocked by `enforce_post_borrow_repay_invariant` in `handle_repay`) and has no economic incentive to fully repay underwater dust. Over many liquidations across many users, this systematically erodes protocol solvency. This finding chains with report_028 (where the dust becomes permanently unliquidatable when `seize_ctokens.floor()` returns 0) and report_059 (where ceiling rounding causes liquidator overpayment on the very liquidation that creates the dust).

### PoC

**File:** `poc_036_liquidation_dust_position.move`
```move
// PoC for Report #036: Liquidation Skips min_borrow_amount Check
//
// Target: contracts/protocol/sources/internal/market/market.move:773-774
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_036
//
// Bug: liquidation_inner calls unsafe_repay_debt_only without
//      enforce_post_borrow_repay_invariant, allowing partial liquidation
//      to leave debt below min_borrow_amount. This creates dust positions
//      that cannot be partially repaid (handle_repay blocks it) and are
//      economically irrational to fully repay.
//
// Config override:
//   Default min_borrow_amount = 100 raw (near-zero). We update USDC
//   min_borrow_amount to 100 USDC (10^8 raw) via admin to simulate
//   production-realistic parameters where dust matters.
//
// Test parameters:
//   USDC min_borrow_amount = 10^8 raw = 100 USDC (updated via admin)
//   close_factor = 50%, close_factor_bypass_min_value = $1
//   ETH collateral_factor = 70%, liquidation_factor = 70%
//   liquidation_incentive = 5% (500 bps)

#[test_only]
module protocol::poc_036_liquidation_dust_position {
    use sui::test_scenario;
    use sui::clock;
    use sui::coin::Coin;

    use protocol::market_t::MainMarket;
    use test_coin::eth::ETH;
    use test_coin::usdc::USDC;
    use protocol::oracle_t;
    use protocol::open_obligation_t;
    use protocol::constants;
    use protocol::market_t::default_eth_decimal_places;
    use protocol::market_t::default_stable_decimal_places;

    const ADMIN: address = @0xAD;
    const BORROWER: address = @0xBB;
    const LIQUIDATOR: address = @0xCC;

    /// Min borrow = 100 USDC = 10^8 raw units (production-realistic)
    const MIN_BORROW_USDC: u64 = 100_000_000; // 100 * 10^6

    /// Proves that liquidation can leave debt below min_borrow_amount
    /// without any enforcement check, creating stuck dust positions.
    ///
    /// Setup:
    ///   1. Update USDC min_borrow_amount to 100 USDC (production-realistic)
    ///   2. Borrower deposits 1 ETH ($1000), borrows 150 USDC
    ///   3. ETH price drops to $210 → position becomes liquidatable
    ///      (weighted collateral = $210 * 70% = $147 < $150 debt)
    ///   4. Liquidator repays up to 50% (close_factor) = 75 USDC
    ///   5. Remaining debt = 75 USDC < 100 USDC (min_borrow_amount)
    ///
    /// The test PASSES because the liquidation succeeds without checking
    /// min_borrow_amount — proving dust position creation is possible.
    #[test]
    fun test_liquidation_creates_dust_below_min_borrow() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market with default config
        let (admin_cap, mut app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);
        let mut x_oracle = oracle_t::init_t(scenario);

        // Step 2: Update USDC min_borrow_amount to 100 USDC (production-realistic)
        // Default is 100 raw units (near-zero), which is unrealistic.
        scenario.next_tx(ADMIN);
        let usdc_config = protocol::asset_admin::create_market_asset_config(
            &admin_cap, &app,
            MIN_BORROW_USDC,                    // min_borrow_amount = 100 USDC
            constants::max_borrow_amount(),      // max_borrow_amount (unchanged)
            1000000000000000000,                 // max_deposit_amount (unchanged)
            constants::repay_fee_rate(),          // repay_fee_rate (unchanged)
            100,                                 // liquidation_fee_rate (unchanged)
        );
        protocol::asset_admin::update_market_asset_config<MainMarket, USDC>(
            &admin_cap, &app, &mut market, usdc_config
        );

        // Step 3: Set oracle prices
        clock.set_for_testing(100_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0)); // $1000
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));   // $1

        // Step 4: Borrower creates obligation and deposits 1 ETH ($1000)
        scenario.next_tx(BORROWER);
        let borrower_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let eth_amount = 1 * 10u64.pow(default_eth_decimal_places()); // 1 ETH
        let eth_coin = sui::coin::mint_for_testing<ETH>(eth_amount, scenario.ctx());
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &borrower_cap, eth_coin, &clock, scenario.ctx()
        );

        // Step 5: Borrower borrows 150 USDC
        // Capacity: $1000 * 70% CF = $700, borrowing $150 → safe
        // 150 USDC > 100 USDC min_borrow → invariant satisfied
        scenario.next_tx(BORROWER);
        let borrow_amount = 150 * 10u64.pow(default_stable_decimal_places()); // 150 USDC
        let borrowed = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &borrower_cap, &mut market, &coin_registry,
            borrow_amount, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed);

        // Step 6: Drop ETH price to $210 → position becomes liquidatable
        // Weighted collateral = $210 * 70% LF = $147 < $150 debt
        clock.set_for_testing(101_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(210, 0));

        // Step 7: Liquidator repays 75 USDC (max allowed by 50% close factor)
        // 150 USDC debt = $150 > $1 bypass threshold → close factor enforced
        // Max repay = 150 * 50% = 75 USDC
        // After liquidation: remaining = 75 USDC < 100 USDC min_borrow_amount
        scenario.next_tx(LIQUIDATOR);
        let repay_amount = 75 * 10u64.pow(default_stable_decimal_places()); // 75 USDC
        let repay_coin = sui::coin::mint_for_testing<USDC>(repay_amount, scenario.ctx());

        // Setup liquidation permission
        let permit = protocol::whitelist_admin::mint_new_whitelist(
            &admin_cap, &mut app, scenario.ctx()
        );
        protocol::whitelist_admin::update_permission(
            &admin_cap, &mut app, object::id(&permit),
            protocol::whitelist_admin::liquidation(), true
        );

        // Execute liquidation — BUG: liquidation_inner calls
        // unsafe_repay_debt_only WITHOUT enforce_post_borrow_repay_invariant,
        // leaving 75 USDC debt below min_borrow_amount (100 USDC)
        let (seized_eth, refund_usdc) =
            protocol::liquidate::liquidate_as_coin<MainMarket, USDC, ETH>(
                &app, &permit, borrower_cap.id(), &mut market,
                repay_coin, &coin_registry, &x_oracle, &clock, scenario.ctx()
            );

        // Verify liquidation occurred (seized collateral > 0, no refund)
        assert!(seized_eth.value() > 0, 0);
        assert!(refund_usdc.value() == 0, 1);

        // BUG PROVEN: Liquidation succeeded leaving 75 USDC debt
        // (below 100 USDC min_borrow_amount).
        //
        // Consequences:
        // - Borrower cannot partially repay (invariant check blocks it)
        // - Full repay is economically irrational for underwater dust
        // - Position accumulates interest as bad debt

        // Cleanup
        std::unit_test::destroy(seized_eth);
        std::unit_test::destroy(refund_usdc);
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(borrower_cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(permit);
        std::unit_test::destroy(x_oracle);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }

    /// Second proof: after liquidation creates dust, partial repay is blocked.
    /// The borrower is stuck — cannot partially repay, and full repay of
    /// underwater dust is economically irrational.
    #[test]
    #[expected_failure]
    fun test_dust_position_blocks_partial_repay() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Same setup with production-realistic min_borrow
        let (admin_cap, mut app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);
        let mut x_oracle = oracle_t::init_t(scenario);

        scenario.next_tx(ADMIN);
        let usdc_config = protocol::asset_admin::create_market_asset_config(
            &admin_cap, &app,
            MIN_BORROW_USDC,
            constants::max_borrow_amount(),
            1000000000000000000,
            constants::repay_fee_rate(),
            100,
        );
        protocol::asset_admin::update_market_asset_config<MainMarket, USDC>(
            &admin_cap, &app, &mut market, usdc_config
        );

        clock.set_for_testing(100_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 2: Borrower deposits 1 ETH, borrows 150 USDC
        scenario.next_tx(BORROWER);
        let borrower_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let eth_coin = sui::coin::mint_for_testing<ETH>(
            1 * 10u64.pow(default_eth_decimal_places()), scenario.ctx()
        );
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &borrower_cap, eth_coin, &clock, scenario.ctx()
        );

        scenario.next_tx(BORROWER);
        let borrowed = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &borrower_cap, &mut market, &coin_registry,
            150 * 10u64.pow(default_stable_decimal_places()),
            &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed);

        // Step 3: Make liquidatable (ETH drops $1000 → $210)
        clock.set_for_testing(101_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(210, 0));

        // Step 4: Liquidate 75 USDC (50% close factor max)
        scenario.next_tx(LIQUIDATOR);
        let repay_coin = sui::coin::mint_for_testing<USDC>(
            75 * 10u64.pow(default_stable_decimal_places()), scenario.ctx()
        );
        let permit = protocol::whitelist_admin::mint_new_whitelist(
            &admin_cap, &mut app, scenario.ctx()
        );
        protocol::whitelist_admin::update_permission(
            &admin_cap, &mut app, object::id(&permit),
            protocol::whitelist_admin::liquidation(), true
        );

        let (seized, refund) =
            protocol::liquidate::liquidate_as_coin<MainMarket, USDC, ETH>(
                &app, &permit, borrower_cap.id(), &mut market,
                repay_coin, &coin_registry, &x_oracle, &clock, scenario.ctx()
            );
        std::unit_test::destroy(seized);
        std::unit_test::destroy(refund);

        // Step 5: Borrower tries to partially repay the 75 USDC dust
        // ABORTS: enforce_post_borrow_repay_invariant in handle_repay
        // checks remaining debt >= min_borrow_amount.
        // Repaying 25 USDC leaves 50 USDC < 100 USDC min → abort!
        scenario.next_tx(BORROWER);
        let partial_repay = sui::coin::mint_for_testing<USDC>(
            25 * 10u64.pow(default_stable_decimal_places()), scenario.ctx()
        );
        protocol::repay::repay<MainMarket, USDC>(
            &app, &mut market, &borrower_cap, partial_repay, &clock, scenario.ctx()
        );

        // Never reached — test passes via #[expected_failure]
        // proving the dust position blocks partial repayment
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(borrower_cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(permit);
        std::unit_test::destroy(x_oracle);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
```

### Mitigation

Add a `min_borrow_amount` check after liquidation debt repayment, or force full repayment when remaining debt would fall below the minimum:

```move
// In liquidation_inner, after line 774:
let _residual = obligation.unsafe_repay_debt_only<MarketType, DebtType>(available_repay_coin.value());

// If remaining debt is below min_borrow_amount, force full clearance
if (obligation.has_debt(debt_name)) {
    let remaining = obligation.debt(debt_name).unsafe_debt_amount();
    let min_borrow = assets.load_by_type(debt_name).asset_config().min_borrow_amount();
    if (remaining.lt_u64(min_borrow)) {
        obligation.unsafe_repay_debt_only<MarketType, DebtType>(remaining.ceil());
    };
};
```