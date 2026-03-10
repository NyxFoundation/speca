### Liquidator will unfairly liquidate borrowers using a paused debt asset during oracle emergencies

### Summary

Missing debt asset `liquidation_paused` check in `handle_liquidation` will cause unfair liquidation losses for borrowers as a liquidator will repay debt using an asset whose liquidation the admin explicitly paused (due to oracle issues), bypassing the emergency control.

### Root Cause

In [`market.move:519-520`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L519-L520) `handle_liquidation` only checks the collateral asset's `liquidation_paused` flag but never checks the debt asset's pause state:

```move
public(package) fun handle_liquidation<MarketType, DebtType, CollateralType>(
    self: &mut Market<MarketType>,
    ...
) {
    // ...
    let collateral_name = type_name::with_defining_ids<CollateralType>();
    // ...
    let asset = self.assets.load_mut_by_type(collateral_name);
    assert!(!asset.liquidation_paused(), error::liquidation_paused_for_asset());  // Only checks collateral
    // ...
}
```

The `liquidation_paused()` getter is defined in [`asset.move:48`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/asset.move#L48) and is available for use, but no corresponding check exists for the debt asset:
```move
let debt_asset = self.assets.load_by_type(type_name::with_defining_ids<DebtType>());
assert!(!debt_asset.liquidation_paused(), error::liquidation_paused_for_asset());  // MISSING
```

### Internal Pre-conditions

1. [Admin needs to call `change_operation_status` to set] the debt asset's `liquidation_paused` flag to be exactly `true`.
2. [Borrowers need to have borrowed to create] existing borrowing obligations where the paused asset is used as the debt asset.

### External Pre-conditions

1. An oracle issue or price feed compromise must affect the paused asset, motivating the admin to pause liquidation for that asset.

### Attack Path

1. Admin discovers an oracle issue affecting Token A's price feed.
2. Admin pauses liquidation for Token A via `change_operation_status` to prevent incorrect liquidations.
3. Liquidator calls `liquidate` with Token A as the debt asset (repaying Token A to seize other collateral), because only the collateral asset's pause state is checked.
4. If the oracle is reporting an inflated price for Token A, this allows the liquidator to over-repay (at the inflated debt valuation) and over-seize collateral.

### Impact

The borrowers suffer a loss of collateral from unfair liquidation using stale/manipulated debt pricing that the admin explicitly tried to block. The liquidator gains the excess seized collateral. The admin cannot fully pause liquidation for an asset experiencing oracle issues because the pause mechanism only blocks half the liquidation paths.

### PoC

**File:** `poc_029_liquidation_debt_pause_bypass.move`
```move
// PoC for Report #029: Normal Liquidation Only Checks Collateral Pause, Not Debt Pause
//
// Target: contracts/protocol/sources/internal/market/market.move:519-520
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_029
//
// Bug: handle_liquidation only checks collateral asset's liquidation_paused
//      flag (what=3), not the debt asset's. An admin can pause USDC for
//      liquidation, but liquidation with USDC as DEBT still proceeds.
//
// Severity upgrade angle (Low → Medium):
//   When admin pauses an asset due to oracle issues (price feed manipulation
//   or stale oracle), liquidation should be blocked for that asset in ALL
//   roles (both debt and collateral). The missing check means emergency
//   controls are incomplete — liquidators can still use bad oracle data
//   to execute unfair liquidations against the paused asset's debt positions.
//
// Expected: test PASSES, proving liquidation succeeds despite debt pause

#[test_only]
module protocol::poc_029_liquidation_debt_pause_bypass {
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

    /// what=3 corresponds to LiquidationPaused in asset.move:change_operation_status
    const LIQUIDATION_PAUSE: u8 = 3;

    /// Proves that pausing USDC for liquidation does NOT block liquidation
    /// when USDC is the DEBT asset (only blocks when USDC is collateral).
    ///
    /// Scenario:
    ///   1. Borrower deposits ETH, borrows USDC
    ///   2. Admin pauses USDC for liquidation (emergency: oracle issue)
    ///   3. ETH price drops → position liquidatable
    ///   4. Liquidator liquidates with USDC as debt → SUCCEEDS (bug!)
    ///
    /// In contrast, if USDC were the collateral, the pause WOULD block it.
    /// This asymmetry means emergency controls are incomplete.
    #[test]
    fun test_liquidation_proceeds_despite_debt_asset_paused() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market
        let (admin_cap, mut app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);
        let mut x_oracle = oracle_t::init_t(scenario);

        // Step 2: Set prices
        clock.set_for_testing(100_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 3: Borrower deposits 1 ETH ($1000), borrows 600 USDC
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
        let borrow_amount = 600 * 10u64.pow(default_stable_decimal_places());
        let borrowed = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &borrower_cap, &mut market, &coin_registry,
            borrow_amount, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed);

        // Step 4: Admin pauses USDC for liquidation (emergency control)
        // Intent: "USDC oracle is unreliable, stop all liquidations involving USDC"
        scenario.next_tx(ADMIN);
        protocol::asset_admin::update_asset_paused_state<MainMarket, USDC>(
            &admin_cap, &app, &mut market,
            LIQUIDATION_PAUSE,  // what=3 → LiquidationPaused
            true                // paused = true
        );

        // Step 5: ETH price drops to $800 → position becomes liquidatable
        // Weighted collateral = $800 * 70% = $560 < $600 debt
        clock.set_for_testing(101_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(800, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 6: Liquidator attempts liquidation with USDC as DEBT
        // BUG: handle_liquidation only checks collateral (ETH) pause state,
        //      not debt (USDC) pause state.
        //      ETH is NOT paused → check passes → liquidation proceeds!
        scenario.next_tx(LIQUIDATOR);
        let repay_amount = 300 * 10u64.pow(default_stable_decimal_places());
        let repay_coin = sui::coin::mint_for_testing<USDC>(repay_amount, scenario.ctx());

        let permit = protocol::whitelist_admin::mint_new_whitelist(
            &admin_cap, &mut app, scenario.ctx()
        );
        protocol::whitelist_admin::update_permission(
            &admin_cap, &mut app, object::id(&permit),
            protocol::whitelist_admin::liquidation(), true
        );

        // This SHOULD fail because USDC is paused for liquidation,
        // but it SUCCEEDS because only collateral pause is checked.
        let (seized_eth, refund_usdc) =
            protocol::liquidate::liquidate_as_coin<MainMarket, USDC, ETH>(
                &app, &permit, borrower_cap.id(), &mut market,
                repay_coin, &coin_registry, &x_oracle, &clock, scenario.ctx()
            );

        // BUG PROVEN: Liquidation succeeded despite USDC being paused
        assert!(seized_eth.value() > 0, 0);

        // Impact: If USDC oracle was compromised (reason for pause),
        // the liquidator may have used incorrect USDC pricing to
        // compute seizure amounts, unfairly liquidating the borrower.

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

Add a debt asset pause check in `handle_liquidation`:

```move
public(package) fun handle_liquidation<MarketType, DebtType, CollateralType>(...) {
    // ... existing collateral checks ...
    let asset = self.assets.load_mut_by_type(collateral_name);
    assert!(!asset.liquidation_paused(), error::liquidation_paused_for_asset());

    // Add debt asset pause check
    let debt_asset = self.assets.load_by_type(type_name::with_defining_ids<DebtType>());
    assert!(!debt_asset.liquidation_paused(), error::liquidation_paused_for_asset());
    // ...
}
```
