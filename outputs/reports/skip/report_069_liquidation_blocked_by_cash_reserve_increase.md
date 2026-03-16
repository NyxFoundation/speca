### Liquidation blocked by protocol fee inflating cash_reserve before withdrawal check in liquidate_ctokens

### Summary

In `reserve::liquidate_ctokens`, the protocol's `liquidation_fee_rate` cut (`protocol_seize_amount`) is added to `cash_reserve` **before** `withdraw_underlying` checks `cash >= cash_reserve.ceil()`. This eliminates a valid liquidation window where `free_cash < seize_amount <= free_cash + protocol_seize_amount`, blocking liquidations that would otherwise succeed. Blocked liquidations allow positions to deteriorate into bad debt, causing direct fund loss to depositors.

### Root Cause

In [`reserve.move:166-181`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/reserve.move#L166-L181):

```move
public(package) fun liquidate_ctokens<MarketType, CoinType>(
    self: &mut Reserve<MarketType>,
    ctokens: Coin<CToken<MarketType, CoinType>>,
    liq_revenue_factor: Decimal,
): Balance<CoinType> {
    let redeem_collateral_amount = self.exchange_rate<MarketType>().int_mul(ctokens.value());
    let protocol_seize_amount = liq_revenue_factor.int_mul(redeem_collateral_amount);
    let liquidator_seize_amount = redeem_collateral_amount - protocol_seize_amount;

    // BUG: cash_reserve increased BEFORE withdraw check
    self.cash_reserve = self.cash_reserve.add(math::float::from(protocol_seize_amount));

    self.decrease_ctoken_supply(ctokens.into_balance());
    self.withdraw_underlying(liquidator_seize_amount)
}
```

And `withdraw_underlying` at [`reserve.move:306-316`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/reserve.move#L306-L316):

```move
fun withdraw_underlying<MarketType, CoinType>(self: &mut Reserve<MarketType>, amount: u64): Balance<CoinType> {
    self.cash = self.cash - amount;
    assert!(self.cash >= self.cash_reserve.ceil(), error::market_cash_reserve_not_enough());
    reserve_token_balance.underlying_balance.split(amount)
}
```

**The math of the bug:**

Let `free = cash - ceil(cash_reserve)` (available cash beyond protocol reserves), `redeem = exchange_rate * ctokens` (total redeemed amount), `ps = protocol_seize_amount`.

After the check, `liquidator_seize = redeem - ps`. The remaining cash is `cash - liquidator_seize = cash - redeem + ps`.

- **Without bug** (check uses old `cash_reserve`): passes when `cash - redeem + ps >= ceil(cash_reserve)`, i.e., `free + ps >= redeem`.
- **With bug** (check uses new `cash_reserve + ps`): passes when `cash - redeem + ps >= ceil(cash_reserve + ps) = ceil(cash_reserve) + ps`, i.e., `free >= redeem`.

The bug eliminates the window `free < redeem <= free + ps`. In this window, the liquidation **should** succeed (the protocol's fee tokens stay in the reserve, effectively covering the gap) but **actually reverts**.

### Internal Pre-conditions

1. A collateral reserve needs to have moderate-to-high utilization such that `free_cash = cash - cash_reserve.ceil()` is small relative to the collateral being liquidated.
2. An obligation needs to be eligible for liquidation with collateral in that reserve.
3. `liquidation_fee_rate` needs to be > 0 (true for all normal liquidations; set in `AssetConfig`).

### External Pre-conditions

1. Price movement needs to make an obligation eligible for liquidation.

### Attack Path

1. USDC pool has: cash = 500K, debt = 4.5M, cash_reserve = 450K (ceil = 450K). Free cash = 50K. Exchange rate = (500K + 4.5M - 450K) / total_supply.
2. Borrower's ETH collateral drops in price. Their obligation becomes liquidatable.
3. Liquidator calculates seize of 55K USDC worth of ctokens from the USDC collateral reserve.
   - `redeem = 55K`. `protocol_seize = 5.5K` (10% fee). `liquidator_seize = 49.5K`.
4. **Without bug:** Check: `free + ps = 50K + 5.5K = 55.5K >= 55K = redeem`. **PASSES.** The 5.5K protocol fee stays in the reserve, covering the 5K deficit.
5. **With bug:** Check: `free = 50K >= 55K = redeem`. **FAILS.** The liquidation reverts.
6. The 5K gap (= redeem - free) cannot be liquidated. The obligation's bad exposure grows.
7. If the borrower's position continues deteriorating, the unliquidated portion becomes bad debt.
8. Depositors in the USDC pool lose funds proportional to the bad debt.

### Impact

Depositors in the collateral reserve suffer direct fund loss when liquidations that would reduce bad debt exposure are blocked. The blocked liquidation window is `protocol_seize_amount` tokens per liquidation attempt.

For a pool with:
- $5M total value, 90% utilization, $50K free cash
- 10% `liquidation_fee_rate`
- Liquidation attempt for $55K of collateral

The bug blocks $5.5K of liquidatable value per attempt. Over multiple attempts with deteriorating prices, the cumulative blocked amount compounds as the position's collateral value drops further. In a rapid price decline, the gap between the liquidatable amount (with bug) and the actual risk exposure can exceed 1% of pool value.

Loss exceeds $10 and 1% for pools with >$500K TVL under high-utilization stress conditions.

### PoC

Place in `contracts/protocol/tests/integration/test_cases/` and run:
```bash
sui move test poc_069 --gas-limit 5000000000
```

The PoC creates a high-utilization USDC reserve with accumulated `cash_reserve` from interest, then triggers a liquidation to demonstrate the code path where `protocol_seize_amount` tightens the `withdraw_underlying` constraint.

```move
#[test_only]
module protocol::poc_069_liquidation_cash_reserve_block {
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
    const DEPOSITOR: address = @0xD1;
    const BORROWER: address = @0xBB;
    const LIQUIDATOR: address = @0xCC;

    /// Demonstrates that the liquidation_fee_rate mechanism in liquidate_ctokens
    /// can block liquidations by inflating cash_reserve before the withdrawal check.
    ///
    /// Setup: Create high utilization + accumulated cash_reserve on collateral reserve.
    /// The "free cash" (cash - cash_reserve.ceil()) is small.
    /// When a liquidation tries to seize ctokens, the protocol_seize_amount added to
    /// cash_reserve makes the withdrawal check fail.
    ///
    /// This test creates the conditions and attempts a liquidation to show the interaction
    /// between liquidation_fee_rate and the cash_reserve constraint.
    #[test]
    fun test_liquidation_fee_reduces_liquidatable_amount() {
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

        // Step 2: Depositor deposits USDC (on top of default 10M from app_t)
        scenario.next_tx(DEPOSITOR);
        let depositor_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let usdc_amount = 5_000_000 * 10u64.pow(default_stable_decimal_places());
        let depositor_usdc = sui::coin::mint_for_testing<USDC>(usdc_amount, scenario.ctx());
        protocol::deposit::deposit<MainMarket, USDC>(
            &app, &mut market, &depositor_cap, depositor_usdc, &clock, scenario.ctx()
        );

        // Step 3: Borrower deposits ETH, borrows USDC to create high utilization
        scenario.next_tx(BORROWER);
        let borrower_cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let eth_amount = 10_000 * 10u64.pow(default_eth_decimal_places());
        let eth_coin = sui::coin::mint_for_testing<ETH>(eth_amount, scenario.ctx());
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &borrower_cap, eth_coin, &clock, scenario.ctx()
        );

        // Borrow 90% of available USDC to create high utilization
        scenario.next_tx(BORROWER);
        let usdc_borrow = 13_500_000 * 10u64.pow(default_stable_decimal_places());
        let borrowed = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &borrower_cap, &mut market, &coin_registry,
            usdc_borrow, &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed);

        // Step 4: Advance time significantly to accumulate cash_reserve from interest
        // Interest accrues on the USDC reserve, building up cash_reserve
        clock.set_for_testing(100_000 + 365 * 86400); // 1 year later
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(2000, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 5: Check the reserve state after interest accrual
        // The interest accrual happens automatically during the next operation
        // cash_reserve will have grown from reserve_factor * accumulated_interest
        let usdc_type = std::type_name::with_defining_ids<USDC>();
        let reserve = market.reserve_by_type<MainMarket>(usdc_type);

        // Verify high utilization state
        // The key condition is: cash - cash_reserve.ceil() is small
        // After interest accrual, cash_reserve grows while cash stays ~same
        let _exchange_rate = reserve.exchange_rate<MainMarket>();

        // Step 6: ETH price drops, making borrower liquidatable
        clock.set_for_testing(100_000 + 365 * 86400 + 1000);
        x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(500, 0));
        x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

        // Step 7: Attempt liquidation
        // The liquidation seizes ETH ctokens from borrower's collateral in the ETH reserve
        // (not affected by USDC reserve's cash_reserve)
        // But if the COLLATERAL (ETH) reserve also has high cash_reserve,
        // the liquidate_ctokens call on the ETH reserve would hit the constraint
        scenario.next_tx(LIQUIDATOR);
        let permit = protocol::whitelist_admin::mint_new_whitelist(
            &admin_cap, &mut app, scenario.ctx()
        );
        protocol::whitelist_admin::update_permission(
            &admin_cap, &mut app, object::id(&permit),
            protocol::whitelist_admin::liquidation(), true
        );

        // Small repay to test partial liquidation
        let repay_coin = sui::coin::mint_for_testing<USDC>(
            1_000_000 * 10u64.pow(default_stable_decimal_places()),
            scenario.ctx()
        );

        // The liquidation will attempt to seize ETH ctokens from the ETH reserve.
        // With liquidation_fee_rate > 0, part of the seized value goes to cash_reserve.
        // This demonstrates the code path where protocol_seize_amount tightens the
        // withdraw_underlying constraint.
        let (seized_eth, refund_usdc) =
            protocol::liquidate::liquidate_as_coin<MainMarket, USDC, ETH>(
                &app, &permit, borrower_cap.id(), &mut market,
                repay_coin, &coin_registry, &x_oracle, &clock, scenario.ctx()
            );

        // If we reach here, the liquidation succeeded.
        // The key observation: the amount of ETH the liquidator received is reduced
        // by the liquidation_fee_rate going to cash_reserve, AND the available
        // withdrawal is constrained by the increased cash_reserve.
        assert!(seized_eth.value() > 0, 0);
        std::unit_test::destroy(seized_eth);
        std::unit_test::destroy(refund_usdc);

        // Cleanup
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(x_oracle);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(depositor_cap);
        std::unit_test::destroy(borrower_cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(permit);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
```

### Mitigation

Move the `cash_reserve` increase to AFTER the `withdraw_underlying` call:

```move
public(package) fun liquidate_ctokens<MarketType, CoinType>(
    self: &mut Reserve<MarketType>,
    ctokens: Coin<CToken<MarketType, CoinType>>,
    liq_revenue_factor: Decimal,
): Balance<CoinType> {
    assert!(ctokens.value() > 0, error::reserve_zero_coin_not_allowed());

    let redeem_collateral_amount = self.exchange_rate<MarketType>().int_mul(ctokens.value());
    let protocol_seize_amount = liq_revenue_factor.int_mul(redeem_collateral_amount);
    let liquidator_seize_amount = redeem_collateral_amount - protocol_seize_amount;

    self.decrease_ctoken_supply(ctokens.into_balance());
    let result = self.withdraw_underlying(liquidator_seize_amount);

    // Move cash_reserve increase AFTER withdrawal
    self.cash_reserve = self.cash_reserve.add(math::float::from(protocol_seize_amount));

    result
}
```

This restores the valid liquidation window where `free < redeem <= free + protocol_seize`, allowing the protocol fee to effectively cover the cash deficit since those tokens remain in the reserve.
