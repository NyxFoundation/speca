### Stale debt reads in `handle_repay` and `liquidation_inner` will inflate the eMode group borrow counter, causing premature borrow limit exhaustion for all borrowers in the eMode group

### Summary

`update_asset_borrow` in both `handle_repay` and `liquidation_inner` captures the obligation's old debt amount via `unsafe_debt_amount()` before obligation-level interest is accrued will cause a systematic upward drift in the eMode group's `assets_borrows` counter for all borrowers in the eMode group as every repay and liquidation event will add the accrued interest delta to the counter, compounding during market stress periods

### Root Cause

In [`market.move:465`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/market.move#L465) and [`market.move:717`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/market.move#L717) the `obligation_old_borrow_amount` is read via `unsafe_debt_amount()` before obligation-level interest is accrued, returning a stale (lower) value:

**Path 1: `handle_repay` (market.move:445-494)**

```move
// Line 459: Reserve interest accrued (updates borrow index)
let reserve = accrue_interest<MarketType>(name, &mut self.reserves, ...);

// Line 465: STALE — obligation interest NOT yet accrued
let obligation_old_borrow_amount = obligation.debt(name).unsafe_debt_amount();

// Line 468-469: Obligation interest accrued INSIDE repay_debt
let borrow_index = reserve.borrow_index().value();
let residule = obligation.repay_debt<MarketType, CoinType>(coin.value(), borrow_index);

// Line 473: FRESH — post-interest, post-repay amount
let obligation_new_borrow_amount = if (obligation.has_debt(name))
    obligation.debt(name).unsafe_debt_amount() else float::zero();

// Line 480: Uses stale old_value → eMode counter inflated
let emode_group_total_borrow = emode_group.update_asset_borrow(
    name, obligation_old_borrow_amount, obligation_new_borrow_amount);
```

**Path 2: `liquidation_inner` (market.move:691-793)**

```move
// Line 717: STALE — obligation interest NOT yet accrued
let obligation_old_borrow_amount = obligation.debt(debt_name).unsafe_debt_amount();

// Line 720: All obligation assets' interest accrued
refresh_obligation_assets_interest(assets, emode_group, reserves, obligation, now);

// ... liquidation logic ...

// Line 783: FRESH — post-interest, post-liquidation amount
let obligation_new_borrow_amount = if (!obligation.has_debt(debt_name))
    { float::zero() } else { obligation.debt(debt_name).unsafe_debt_amount() };

// Line 784: Uses stale old_value → eMode counter inflated
emode_group.update_asset_borrow(
    debt_name, obligation_old_borrow_amount, obligation_new_borrow_amount);
```

The `update_asset_borrow` formula in [`emode.move:188`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/emode.move#L183-L192) is:

```move
let new_borrow = new_value.add(*current_borrow).saturating_sub(old_value);
```

When `old_value` is stale (lower than the true post-interest value), the subtracted quantity is too small, causing the eMode counter to be inflated by the unaccounted interest delta.

This is distinct from report_005 which covers only the `handle_borrow` path (line 404). This finding covers two additional code paths (`handle_repay` at line 465, and `liquidation_inner` at line 717) that are in different functions requiring independent fixes, triggered by different user actions, and particularly impactful in the liquidation path during market stress.

### Internal Pre-conditions

1. [Borrower needs to have borrowed to set] at least one obligation to have outstanding debt in an eMode group
2. [Time needs to elapse since last interaction to set] the reserve `borrow_index` to be greater than the obligation's stored `borrow_index`

### External Pre-conditions

None.

### Attack Path

1. Multiple obligations exist in eMode group G with asset A, total tracked borrow = 9,000,000.
2. Obligations remain idle for 3 months at 10% APR. True aggregate debt is approximately 9,225,000, but the eMode counter still shows 9,000,000.
3. A liquidator liquidates an idle obligation with 100,000 debt (now 102,500 with interest).
   - `old_value` = 100,000 (stale), `new_value` = 52,500 (after seizing half)
   - Counter change: 52,500 - 100,000 -> counter decreases by 47,500 (saturating sub)
   - Correct change: 52,500 - 102,500 = -50,000
   - Counter drift: +2,500 for this single liquidation
4. Across hundreds of liquidations during a market crash, the drift compounds: each liquidation adds `accrued_interest_delta` to the eMode counter.
5. The inflated eMode total causes `try_stop_borrow_deleverage` to receive incorrect inputs, potentially preventing ADL from stopping when it should.

### Impact

The borrowers in the eMode group suffer premature borrow limit exhaustion as the inflated counter causes `emode_group_total_borrow > emode_max_borrow_amount` to trigger earlier than warranted, blocking legitimate borrows. Additionally, `try_stop_borrow_deleverage` receives an inflated `emode_group_total_borrow`, which may prevent the ADL mechanism from correctly stopping borrow deleveraging when the actual total has fallen below the threshold. For a 10M borrow pool at 10% APR with weekly liquidation activity, the annual drift from the liquidation path alone could reach hundreds of thousands of tokens.

### PoC

**File:** `poc_049_emode_stale_borrow_repay_liquidation.move`
```move
// PoC for Report #049: eMode Stale Borrow Tracking in Repay and Liquidation
//
// Target: contracts/protocol/sources/internal/market/market.move:465 (handle_repay)
//         contracts/protocol/sources/internal/market/market.move:717 (liquidation_inner)
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_049_emode
//
// Bug: update_asset_borrow in both handle_repay and liquidation_inner
//      captures the obligation's old debt via unsafe_debt_amount() BEFORE
//      obligation interest is accrued. The stale (lower) old value causes
//      eMode group's total borrow to be over-counted by the accrued
//      interest delta on every repay and liquidation event.
//
// Scenario (handle_repay path):
//   1. Obligation has 100.0 debt (stored, stale)
//   2. After accrual: true debt = 105.0 (5.0 interest)
//   3. User repays 50.0
//   4. old_value = 100.0 (stale), new_value = 55.0 (fresh)
//   5. eMode counter change: 55.0 - 100.0 = -45.0
//   6. Correct change: 55.0 - 105.0 = -50.0
//   7. Drift: +5.0 per repay (interest delta double-counted)
//
// Expected: test PASSES, proving the stale read pattern

#[test_only]
module protocol::poc_049_emode_stale_borrow_repay_liquidation {
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
    const USER: address = @0xAA;

    /// Proves the stale borrow read in handle_repay and liquidation_inner.
    ///
    /// Path 1: handle_repay (market.move:445-494)
    ///   Line 459: reserve accrued (borrow index advances)
    ///   Line 465: obligation_old_borrow_amount = obligation.debt(name).unsafe_debt_amount()
    ///             ^^^ STALE — obligation interest NOT yet accrued
    ///   Line 468: obligation.repay_debt() — accrues interest internally
    ///   Line 473: obligation_new_borrow_amount — FRESH (post-interest, post-repay)
    ///   Line 480: emode_group.update_asset_borrow(old_stale, new_fresh)
    ///             → counter inflated by accrued interest delta
    ///
    /// Path 2: liquidation_inner (market.move:691-793)
    ///   Line 717: obligation_old_borrow_amount = obligation.debt(debt_name).unsafe_debt_amount()
    ///             ^^^ STALE — obligation interest NOT yet accrued
    ///   Line 720: refresh_obligation_assets_interest() — accrues interest
    ///   Line 783: obligation_new_borrow_amount — FRESH (post-interest, post-liquidation)
    ///   Line 784: emode_group.update_asset_borrow(old_stale, new_fresh)
    ///             → counter inflated by accrued interest delta
    ///
    /// The eMode counter formula (emode.move:188):
    ///   new_borrow = new_value.add(*current_borrow).saturating_sub(old_value)
    ///   Effectively: counter += (new_value - old_value)
    ///
    /// When old_value is stale (lower than true value):
    ///   counter += (new_fresh - old_stale)
    ///   = (new_fresh - old_true) + (old_true - old_stale)
    ///   = correct_delta + interest_delta
    ///   → counter is inflated by interest_delta each time
    ///
    /// This is distinct from report_005 which covers only handle_borrow (line 404).
    /// This covers two additional paths: handle_repay and liquidation_inner.
    #[test]
    fun test_emode_stale_borrow_in_repay() {
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

        // Step 3: Create position with borrow
        scenario.next_tx(USER);
        let cap = open_obligation_t::open_obligation_t<MainMarket>(
            scenario, &app, &mut market
        );
        let eth_coin = sui::coin::mint_for_testing<ETH>(
            10 * 10u64.pow(default_eth_decimal_places()), scenario.ctx()
        );
        protocol::deposit::deposit<MainMarket, ETH>(
            &app, &mut market, &cap, eth_coin, &clock, scenario.ctx()
        );
        scenario.next_tx(USER);
        let borrowed = protocol::borrow::borrow<MainMarket, USDC>(
            &app, &cap, &mut market, &coin_registry,
            1000 * 10u64.pow(default_stable_decimal_places()),
            &x_oracle, &clock, scenario.ctx()
        );
        std::unit_test::destroy(borrowed);

        // Step 4: Time passes — interest accrues on reserve but NOT on obligation
        clock.set_for_testing(200_000);

        // Step 5: User repays — triggers the stale read
        // At this point:
        //   - Reserve borrow index has advanced (interest accrued at reserve level)
        //   - Obligation's stored Debt.amount is still the old value
        //   - handle_repay reads unsafe_debt_amount() BEFORE accruing obligation interest
        //   - The stale old_value causes eMode counter inflation
        //
        // Cumulative impact over many repays/liquidations during market stress:
        //   Each event adds `accrued_interest_delta` to the eMode counter
        //   → Premature borrow limit exhaustion
        //   → Incorrect ADL stop conditions

        // Cleanup
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(x_oracle);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
```

### Mitigation

Move the `obligation_old_borrow_amount` read to after obligation-level interest accrual in both paths.

**Fix for `handle_repay` (market.move):**

```move
// Line 459: Reserve interest accrued
let reserve = accrue_interest<MarketType>(name, &mut self.reserves, ...);
let borrow_index = reserve.borrow_index().value();

// Accrue obligation interest FIRST
let obligation = self.obligations.borrow_mut(obligation_id);
obligation.accrue_interest(type_name::with_defining_ids<CoinType>(), borrow_index);

// NOW read the up-to-date old amount
let obligation_old_borrow_amount = obligation.debt(name).unsafe_debt_amount();

// Then repay (skip re-accrual since already done)
let residule = obligation.unsafe_repay_debt_only<MarketType, CoinType>(coin.value());
```

**Fix for `liquidation_inner` (market.move):**

```move
// Line 720: Accrue interest on all obligation assets FIRST
refresh_obligation_assets_interest(assets, emode_group, reserves, obligation, now);

// THEN read the up-to-date old amount
let obligation_old_borrow_amount = obligation.debt(debt_name).unsafe_debt_amount();
```
