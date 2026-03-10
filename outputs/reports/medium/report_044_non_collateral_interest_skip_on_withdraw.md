### Depositor will lose accrued interest on withdrawal of non-collateral assets due to skipped interest accrual

### Summary

`refresh_obligation_assets_interest` skipping `accrue_interest` for assets where `can_be_collateral()` returns false will cause a loss of accrued interest for depositors of non-collateral assets as the stale exchange rate in `burn_ctokens` undervalues their cTokens on withdrawal

### Root Cause

In [`market.move:858-886`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L858-L886) the `refresh_obligation_assets_interest` function skips interest accrual for non-collateral assets:

```move
// cannot be collateral, ignore
if (!collateral_settings.can_be_collateral()) { continue };

accrue_interest<MarketType>(name, reserves, asset.asset_config(), asset.interest_model(), now);
```

When `handle_withdraw` (line 308-363) calls this function at line 326, interest is not accrued for the withdrawn non-collateral asset. The subsequent `reserve.burn_ctokens` at line 345 uses the stale exchange rate, which undervalues the user's cTokens.

The exchange rate formula is `(cash + debt - cash_reserve) / total_supply`. Without interest accrual, `debt` is understated (interest not added to outstanding borrows) and `cash_reserve` is understated (protocol revenue not accounted). The net effect is a lower-than-correct exchange rate, meaning fewer underlying tokens per cToken.

### Internal Pre-conditions

1. [Admin needs to configure an eMode group to set] an asset with `can_be_collateral() == false` (i.e., `liquidation_factor == 0`).
2. [Borrowers need to borrow the asset to set] the asset to have active borrows generating interest (otherwise exchange rate is unchanged).
3. [No user needs to interact with the reserve to set] sufficient time elapsed since the last interaction so the stale interest is material.

### External Pre-conditions

None.

### Attack Path

1. Admin configures an eMode group where Asset X has `can_be_collateral = false` (liquidation_factor = 0, but deposits and borrows are permitted).
2. Alice deposits Asset X via `handle_mint` (line 274 correctly calls `accrue_interest`). She receives cTokens at the correct exchange rate.
3. Time passes. Other users borrow Asset X, generating interest that increases the reserve's `debt` and `cash_reserve`.
4. Alice calls `handle_withdraw` for Asset X. `refresh_obligation_assets_interest` at line 326 skips `accrue_interest` for Asset X because it is non-collateral (line 882).
5. `burn_ctokens` at line 345 uses the un-accrued exchange rate, which is lower than the true rate.
6. Alice receives fewer underlying tokens than she is entitled to. The "missing" interest effectively remains in the reserve, benefiting other depositors or protocol reserves.

### Impact

The depositors of non-collateral assets suffer a loss of all accrued interest on withdrawal. The magnitude scales with the interest rate on the asset, the time since the reserve was last touched by any operation, and the size of the withdrawal. For assets with high utilization and infrequent interactions, the loss can be material. The worst case occurs for non-collateral assets with few market participants and long periods between any interaction.

### PoC

**File:** `poc_044_non_collateral_interest_skip.move`
```move
// PoC for Report #044: Non-Collateral Deposit Interest Skip on Withdraw
//
// Target: contracts/protocol/sources/internal/market/market.move:858-886
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_044
//
// Bug: refresh_obligation_assets_interest skips accrue_interest for deposits
// where can_be_collateral() == false (liquidation_factor = 0). When the user
// withdraws, burn_ctokens uses a stale exchange rate, causing the depositor
// to receive fewer underlying tokens than entitled (zero interest earned).

#[test_only]
module protocol::poc_044_non_collateral_interest_skip {
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
    const DEPOSITOR: address = @0xBB;
    const BORROWER: address = @0xCC;

    /// Proves that a depositor of a non-collateral asset earns ZERO interest
    /// despite the asset being actively borrowed for an extended period.
    ///
    /// Setup:
    ///   1. Create eMode group 1 with ETH as non-collateral (liquidation_factor=0)
    ///   2. Depositor enters group 1, deposits 100 ETH
    ///   3. Borrower (default group 0) borrows 50 ETH, generating interest
    ///   4. After 10,000,000 seconds (~115 days), Depositor withdraws all ETH
    ///
    /// Result:
    ///   BUG:   amount_received == 100 ETH (zero interest earned)
    ///   FIXED: amount_received >  100 ETH (interest accrued correctly)
    ///
    /// The test PASSES because the Depositor gets exactly their initial deposit
    /// back with zero interest — proving the stale exchange rate bug.
    #[test]
    fun test_non_collateral_withdrawal_earns_zero_interest() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market with 4 assets and initial liquidity
        let (admin_cap, app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);
        let mut x_oracle = oracle_t::init_t(scenario);

        // Step 2: Create eMode group 1
        clock.set_for_testing(200_000);
        scenario.next_tx(ADMIN);
        protocol::emode_admin::onboard_new_emode_group<MainMarket>(
            &admin_cap, &app, &mut market, 0, &clock, scenario.ctx()
        );

        // Step 3: Onboard ETH to group 1 as NON-COLLATERAL (lf=0, cf=0)
        let dep_lim = protocol::emode_admin::create_limiter(
            &admin_cap, &app, 2u64.pow(63), 10_000_000u32, 10_000_000u32);
        let bor_lim = protocol::emode_admin::create_limiter(
            &admin_cap, &app, 2u64.pow(63), 10_000_000u32, 10_000_000u32);
        let eth_params = protocol::emode_admin::create_emode_params_test(
            &admin_cap,
            0,    // collateral_factor_bps = 0
            0,    // liquidation_factor_bps = 0 → can_be_collateral() returns false
            0,    // liquidation_incentive_bps
            constants::max_borrow_amount(),
            constants::borrow_weight_rate(),
            constants::flash_loan_fee_rate(),
            dep_lim, bor_lim
        );
        protocol::emode_admin::onboard_asset_to_emode_group<MainMarket, ETH>(
            &admin_cap, &app, &mut market, 1, eth_params, scenario.ctx()
        );

        // Step 4: Set oracle prices
        clock.set_for_testing(300_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 5: Depositor enters eMode group 1, deposits 100 ETH (non-collateral)
        let eth_deposit = 100 * 10u64.pow(default_eth_decimal_places()); // 100 ETH
        scenario.next_tx(DEPOSITOR);
        let depositor_cap = protocol::enter_market::create_obligation_with_group<MainMarket>(
            &app, &mut market, 1, scenario.ctx()
        );
        let eth_coin = sui::coin::mint_for_testing<ETH>(eth_deposit, scenario.ctx());
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &depositor_cap, eth_coin, &clock, scenario.ctx()
        );
        // Depositor has 100*10^8 = 10,000,000,000 cETH at exchange_rate=1.0

        // Step 6: Borrower (default group 0) deposits USDC collateral and borrows ETH
        scenario.next_tx(BORROWER);
        let borrower_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let usdc_amount = 100_000 * 10u64.pow(default_stable_decimal_places());
        let usdc_coin = sui::coin::mint_for_testing<USDC>(usdc_amount, scenario.ctx());
        protocol::deposit::deposit<MainMarket, USDC>(
            &app, &mut market, &borrower_cap, usdc_coin, &clock, scenario.ctx()
        );
        scenario.next_tx(BORROWER);
        let eth_borrow = 50 * 10u64.pow(default_eth_decimal_places()); // 50 ETH
        let borrowed = protocol::borrow::borrow<MainMarket, ETH>(
            &app, &borrower_cap, &mut market, &coin_registry,
            eth_borrow, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed);
        // ETH reserve now has 50 ETH of outstanding debt generating interest

        // Step 7: Advance time by 10,000,000 seconds (~115 days)
        // Do NOT touch the ETH reserve — no deposits, borrows, or repays
        clock.set_for_testing(10_000_300_000); // T=10,000,300 seconds (in ms)

        // Step 8: Depositor withdraws ALL ETH cTokens
        // BUG: refresh_obligation_assets_interest (market.move:882) skips
        //      accrue_interest for ETH because can_be_collateral() == false.
        //      burn_ctokens uses stale exchange_rate from T=300 → no interest.
        //
        // The Depositor has no debt, so the safety check (is_obligation_safe)
        // passes without querying any oracle prices.
        scenario.next_tx(DEPOSITOR);
        protocol::withdraw::withdraw<MainMarket, ETH>(
            &app, &mut market, &depositor_cap, &coin_registry,
            eth_deposit, // withdraw all cTokens (minted at 1:1)
            &x_oracle, &clock, scenario.ctx()
        );

        // Step 9: Verify Depositor got EXACTLY initial deposit — ZERO interest
        test_scenario::next_tx(scenario, DEPOSITOR);
        let refunded = scenario.take_from_sender<Coin<ETH>>();

        // BUG PROVEN: amount_received == initial_deposit (no interest earned)
        // After 115 days of lending at ~4.5% utilization, this should be > eth_deposit
        assert!(refunded.value() == eth_deposit, 0);

        // Cleanup
        std::unit_test::destroy(refunded);
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(depositor_cap);
        std::unit_test::destroy(borrower_cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(x_oracle);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
```

### Mitigation

Remove the `can_be_collateral()` check from `refresh_obligation_assets_interest`, or add a separate `accrue_interest` call in `handle_withdraw` before `burn_ctokens`:

```move
// In refresh_obligation_assets_interest, remove the early continue:
// if (!collateral_settings.can_be_collateral()) { continue };
// Always accrue interest for all deposited assets
accrue_interest<MarketType>(name, reserves, asset.asset_config(), asset.interest_model(), now);
```

Alternatively, add a direct interest accrual in `handle_withdraw` before line 344:

```move
let asset = self.assets.load_by_type(name);
accrue_interest<MarketType>(name, &mut self.reserves, asset.asset_config(), asset.interest_model(), now);
let reserve = self.reserves.load_mut_by_type(name);
let deposit = reserve.burn_ctokens<MarketType, CoinType>(ctoken.into_coin(ctx));
```
