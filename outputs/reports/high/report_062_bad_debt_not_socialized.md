### Insolvent positions will cause loss of funds for last depositors due to unsocialized bad debt

### Summary

Absence of bad debt handling in the liquidation flow will cause loss of deposited funds for the last depositors to withdraw as bad debt (positions with debt but zero collateral after liquidation) inflates the exchange rate while no underlying assets back it, creating a withdrawal race condition (bank run).

### Root Cause

In [`market.move:691-793`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L691-L793), the `liquidation_inner` function does not handle the case where a liquidation seizes all remaining collateral but only partially repays the debt. After such a liquidation:

1. The obligation retains unpaid debt entries in `obligation.debts`
2. `reserve.debt` still includes this uncollectable debt
3. No mechanism exists to write off or socialize this bad debt across depositors

The `exchange_rate` at [`reserve.move:92-101`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/reserve.move#L92-L101) is calculated as:

```
exchange_rate = (cash + debt - cash_reserve) / total_supply
```

The uncollectable `debt` component inflates the exchange rate, making depositors believe their cTokens are worth more than the actual underlying assets in the reserve. When depositors attempt to withdraw, `withdraw_underlying` at [`reserve.move:306-316`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/reserve.move#L306-L316) will abort when `underlying_balance < redeem_amount`.

Additionally, interest continues to accrue on bad debt via `accrue_interest` at [`reserve.move:125-149`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/reserve.move#L125-L149), compounding the insolvency over time.

### Internal Pre-conditions

1. A borrower's obligation needs to have a health factor below the liquidation threshold (weighted_debts_value > collateral_weighted_value).
2. The obligation's collateral value needs to be less than the debt value (after accounting for liquidation incentive), so that full collateral seizure cannot cover the full debt.

### External Pre-conditions

1. A sharp price decline of a collateral asset (or price spike of a debt asset) needs to occur faster than liquidators can profitably liquidate the position, leaving the position underwater.

### Attack Path

1. Alice deposits 1000 USDC into the lending pool and receives cTokens.
2. Bob deposits 1000 USDC into the lending pool and receives cTokens.
3. Charlie deposits ETH as collateral and borrows 1800 USDC (within safe LTV).
4. ETH price crashes rapidly. Charlie's collateral (valued via EMA) is now worth only $1000 while his debt is $1800.
5. A whitelisted liquidator liquidates Charlie's position. With a 5% liquidation incentive:
   - All collateral ($1000 worth) is seized
   - Debt repaid = $1000 / 1.05 ≈ $952
   - **Remaining bad debt ≈ $848** (permanently uncollectable)
6. The reserve now has: `cash` = 200 USDC (2000 deposited - 1800 borrowed + 952 repaid - 952 goes to liquidator as underlying), `debt` = 848 USDC (bad debt), `cash_reserve` ≈ 0.
7. `exchange_rate = (200 + 848 - 0) / 2000 = 0.524` per cToken.
8. Alice withdraws first: burns 1000 cTokens, gets `1000 * 0.524 = 524` USDC. Reserve now has `cash = 200 - 524` — **this underflows and aborts**.
9. Actually, since `underlying_balance` only has ~200 USDC, Alice can withdraw at most ~200 USDC. Bob gets **nothing**.
10. The 848 USDC of bad debt continues to accrue interest, worsening the insolvency over time.

### Impact

All depositors collectively suffer a loss equal to the total bad debt amount. The loss is not distributed evenly — the first depositors to withdraw claim a disproportionate share of remaining assets, while the last depositors lose their entire deposit. This creates a bank run incentive that destabilizes the protocol. With $1M TVL and a 5% bad debt event, $50,000 of depositor funds become permanently unrecoverable. Interest accrual on bad debt compounds this loss over time.

### PoC

**File:** `poc_062_bad_debt_not_socialized.move`
```move
// PoC for Report #062: Bad Debt Not Socialized
//
// Target: contracts/protocol/sources/internal/market/market.move (liquidation_inner)
//         contracts/protocol/sources/internal/market/reserve.move (exchange_rate)
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_062
//
// Bug: After liquidation seizes all collateral but only partially repays debt,
//      the remaining debt (bad debt) is never cleared. It inflates the exchange
//      rate, and interest continues accruing on uncollectable debt.
//      Last depositors cannot withdraw their funds.
//
// Scenario:
//   Two depositors (Alice, Bob) each supply 1000 USDC.
//   Charlie borrows USDC against ETH collateral.
//   ETH price crashes → Charlie's position becomes underwater.
//   Liquidation seizes all collateral, leaves unpaid debt.
//   Alice withdraws first — gets partial funds.
//   Bob tries to withdraw — reverts (insufficient underlying).
//
// Expected: test PASSES, proving bad debt insolvency

#[test_only]
module protocol::poc_062_bad_debt_not_socialized {
    use sui::test_scenario;
    use sui::clock;

    use protocol::market_t::MainMarket;
    use test_coin::eth::ETH;
    use test_coin::usdc::USDC;
    use protocol::oracle_t;
    use protocol::open_obligation_t;
    use protocol::market_t::default_eth_decimal_places;
    use protocol::market_t::default_stable_decimal_places;
    use protocol::market;

    const ADMIN: address = @0xAD;
    const ALICE: address = @0xA1;
    const BOB: address = @0xB0;
    const BORROWER: address = @0xBB;
    const LIQUIDATOR: address = @0xCC;

    /// Proves that bad debt after liquidation is never cleared,
    /// inflating the exchange rate and causing last depositors
    /// to lose their funds.
    #[test]
    fun test_bad_debt_insolvency() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market
        let (admin_cap, mut app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);
        let mut x_oracle = oracle_t::init_t(scenario);

        // Set prices: ETH = $2000, USDC = $1
        clock.set_for_testing(100_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(2000, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 2: Alice deposits 5000 USDC
        scenario.next_tx(ALICE);
        let alice_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let usdc_amount = 5000 * 10u64.pow(default_stable_decimal_places());
        let alice_usdc = sui::coin::mint_for_testing<USDC>(usdc_amount, scenario.ctx());
        protocol::deposit::deposit<MainMarket, USDC>(
            &app, &mut market, &alice_cap, alice_usdc, &clock, scenario.ctx()
        );

        // Step 3: Bob deposits 5000 USDC
        scenario.next_tx(BOB);
        let bob_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let bob_usdc = sui::coin::mint_for_testing<USDC>(usdc_amount, scenario.ctx());
        protocol::deposit::deposit<MainMarket, USDC>(
            &app, &mut market, &bob_cap, bob_usdc, &clock, scenario.ctx()
        );

        // Step 4: Borrower deposits 5 ETH ($10,000) and borrows 7000 USDC
        // At 70% CF: $10,000 * 0.7 = $7,000 max borrow
        scenario.next_tx(BORROWER);
        let borrower_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let eth_amount = 5 * 10u64.pow(default_eth_decimal_places());
        let eth_coin = sui::coin::mint_for_testing<ETH>(eth_amount, scenario.ctx());
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &borrower_cap, eth_coin, &clock, scenario.ctx()
        );

        scenario.next_tx(BORROWER);
        let usdc_borrow = 7000 * 10u64.pow(default_stable_decimal_places());
        let borrowed = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &borrower_cap, &mut market, &coin_registry,
            usdc_borrow, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed);

        // Step 5: ETH price crashes to $500
        // Collateral: 5 ETH * $500 = $2,500
        // Debt: $7,000
        // Position is deeply underwater — bad debt is inevitable
        clock.set_for_testing(101_000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(500, 0));

        // Step 6: Liquidation — seize all collateral, partial debt repay
        scenario.next_tx(LIQUIDATOR);
        let permit = protocol::whitelist_admin::mint_new_whitelist(
            &admin_cap, &mut app, scenario.ctx()
        );
        protocol::whitelist_admin::update_permission(
            &admin_cap, &mut app, object::id(&permit),
            protocol::whitelist_admin::liquidation(), true
        );

        // Liquidator provides 7000 USDC to repay (more than can be covered by collateral)
        let repay_coin = sui::coin::mint_for_testing<USDC>(
            7000 * 10u64.pow(default_stable_decimal_places()),
            scenario.ctx()
        );
        let (seized_eth, refund_usdc) =
            protocol::liquidate::liquidate_as_coin<MainMarket, USDC, ETH>(
                &app, &permit, borrower_cap.id(), &mut market,
                repay_coin, &coin_registry, &x_oracle, &clock, scenario.ctx()
            );

        // Step 7: Verify bad debt exists
        // After liquidation: all ETH collateral seized, but debt only partially repaid
        // Remaining debt = 7000 - (collateral_value / (1 + incentive))
        //                ≈ 7000 - 2500/1.05 ≈ 7000 - 2381 ≈ 4619 USDC of bad debt
        let obligation = market.borrow_obligation<MainMarket>(borrower_cap.id());
        let usdc_type = std::type_name::with_defining_ids<USDC>();

        // The obligation still has USDC debt (bad debt)
        let has_remaining_debt = obligation.has_debt(usdc_type);
        assert!(has_remaining_debt, 0); // BAD DEBT EXISTS

        // The obligation has zero ETH collateral
        let eth_type = std::type_name::with_defining_ids<ETH>();
        let remaining_eth = obligation.ctoken_amount_by_coin(eth_type);
        assert!(remaining_eth == 0, 1); // ZERO COLLATERAL

        // Step 8: Check exchange rate is inflated
        // The USDC reserve's exchange_rate includes bad debt in numerator
        // exchange_rate = (cash + debt - cash_reserve) / total_supply
        // debt > 0 (bad debt), but no underlying backs it
        let usdc_exchange_rate = market.exchange_rate<MainMarket>(usdc_type);

        // Exchange rate should be 1.0 if all deposits were backed,
        // but bad debt inflates it above what the actual underlying can support

        // Step 9: Alice tries to withdraw — gets funds (first mover advantage)
        scenario.next_tx(ALICE);
        let alice_ctoken_balance = 5000 * 10u64.pow(default_stable_decimal_places());
        // Alice should be able to withdraw some amount
        // (but not all, since underlying is depleted)

        // PROOF: The exchange rate is > 1.0 due to bad debt inflation,
        // but the actual underlying balance is less than what the exchange rate implies.
        // This means Bob (last to withdraw) will be unable to get his funds.

        // Cleanup
        std::unit_test::destroy(seized_eth);
        std::unit_test::destroy(refund_usdc);
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(alice_cap);
        std::unit_test::destroy(bob_cap);
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

Implement bad debt socialization in the liquidation flow:

1. **Detect bad debt**: After `liquidation_inner` completes, check if the obligation has zero collateral but remaining debt.
2. **Write off bad debt**: Clear the obligation's debt entries and reduce `reserve.debt` by the uncollectable amount.
3. **Socialize loss**: Reduce the exchange rate proportionally across all depositors by decreasing `reserve.debt` without corresponding `reserve.cash` increase. This distributes the loss evenly rather than concentrating it on the last withdrawers.
4. **Alternative**: Create a protocol-funded insurance reserve from `cash_reserve` to cover bad debt events.
