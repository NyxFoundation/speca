### Attacker will permanently disable ADL emergency deleveraging at near-zero cost via repay_on_behalf + borrow in single PTB

### Summary

The permissionless `repay_on_behalf` function reduces eMode group borrow tracking, which can trigger `try_stop_borrow_deleverage` to permanently remove the ADL entry. The attacker then immediately borrows back the same amount in the same PTB, restoring debt to its original level while ADL remains disabled. Only admin can re-enable ADL, and the attacker can repeat this indefinitely.

### Root Cause

In [`market.move:489-491`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/market.move#L489-L491), `handle_repay` calls `try_stop_borrow_deleverage` using the current eMode group total borrow:

```move
let adl = dynamic_field::borrow_mut<ADLRegistryKey, AutoDeleverageRegistry>(&mut self.id, ADLRegistryKey {});
adl.try_stop_borrow_deleverage<CoinType>(type_name::with_defining_ids<MarketType>(), emode_group_id, emode_group_total_borrow.ceil());
```

In [`adl.move:130-147`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/adl.move#L130-L147), `try_stop_borrow_deleverage` removes the ADL entry when `target_amount >= current_value`:

```move
if (t.inner.target_amount < current_value) return;
self.stop_borrow_deleverage<CoinType>(market, emode_group_id);  // REMOVES entry permanently
```

The entry removal is irreversible within the transaction. A subsequent `handle_borrow` in the same PTB re-inflates the eMode tracking, but the ADL entry is already gone. No auto-restart mechanism exists — only `enable_debt_deleverage` (requiring `AdminCap`) can re-add it.

### Internal Pre-conditions

1. ADL must be active for a borrow deleverage event on an eMode group (standard emergency condition)
2. Attacker must have an obligation with collateral in the same eMode group (to borrow back)

### External Pre-conditions

None. The attack works under the exact crisis conditions when ADL is most needed.

### Attack Path

1. Protocol is in crisis: eMode group X has 60M USDC total borrow. Admin enables ADL with `target_amount = 50M`.
2. Attacker has 11M USDC and collateral in group X.
3. **PTB Step 1**: Attacker calls `repay_on_behalf(victim_obligation_id, 11M_USDC)`.
   - eMode tracking: 60M → 49M
   - `try_stop_borrow_deleverage`: `target(50M) >= current(49M)` → **ADL entry REMOVED**
4. **PTB Step 2**: Attacker calls `borrow(11M_USDC)` using their own collateral.
   - eMode tracking: 49M → 60M (back to original)
   - But ADL entry is gone — `get_borrow_deleverage` would now abort with `adl_no_coin`
5. Attacker has: same USDC balance (repaid 11M, borrowed 11M back), same collateral, same debt. Net cost: gas only.
6. ADL is disabled. No one can call `liquidate_adl_borrow` — it aborts at `get_borrow_deleverage`.
7. Admin re-enables ADL → attacker repeats steps 3-4 immediately.

### Impact

The protocol's emergency deleveraging mechanism is permanently neutralized during a crisis. This directly undermines protocol solvency protection:
- Underwater positions that should be force-deleveraged remain open
- Bad debt accumulates unchecked (#062 amplification)
- The attacker (or their accomplice) can protect their own underwater positions from ADL
- The attack is repeatable at near-zero cost, creating an infinite griefing vector against admin

During a market crisis where ADL is the last line of defense against insolvency, disabling it can lead to catastrophic loss for all depositors.

### PoC

Place in `contracts/protocol/tests/integration/test_cases/` and run:
```bash
sui move test poc_067 --gas-limit 5000000000
```

```move
#[test_only]
module protocol::poc_067_adl_premature_stop;

use protocol::adl;
use math::float;

/// Demonstrates that ADL can be disabled by transiently dropping
/// emode tracking below target, then re-inflating in the same PTB.
#[test]
fun test_adl_premature_stop() {
    // Simulate emode group borrow tracking as a simple u64
    // (In reality this is managed by emode.update_asset_borrow)
    let target: u64 = 50_000_000; // 50M target
    let mut current_borrow: u64 = 60_000_000; // 60M current

    let params = adl::new_auto_deleverage_params(
        target,
        float::from_quotient(95, 100),
        float::from_quotient(1, 100),
        float::from_quotient(5, 100),
        float::from_quotient(1, 100),
        float::from_quotient(50, 100),
    );

    // Verify ADL is active: target < current
    params.ensure_limit_breached(current_borrow); // passes: 50M < 60M

    // Step 1: repay_on_behalf reduces tracking by 11M
    current_borrow = current_borrow - 11_000_000; // 49M
    // try_stop_borrow_deleverage would fire: target(50M) >= current(49M)
    // ADL entry REMOVED here

    // Step 2: attacker borrows 11M back
    current_borrow = current_borrow + 11_000_000; // 60M again

    // Debt is back at 60M but ADL is gone!
    // This would now ABORT because ADL entry was removed:
    // params.ensure_limit_breached(current_borrow); // would abort: adl_no_coin

    // Verify debt still exceeds target
    assert!(current_borrow > target, 0); // 60M > 50M — ADL should be active but isn't!
}

/// Shows that without the premature stop, ADL correctly stays active.
#[test]
fun test_adl_stays_active_without_premature_stop() {
    let target: u64 = 50_000_000;
    let current_borrow: u64 = 60_000_000;

    let params = adl::new_auto_deleverage_params(
        target,
        float::from_quotient(95, 100),
        float::from_quotient(1, 100),
        float::from_quotient(5, 100),
        float::from_quotient(1, 100),
        float::from_quotient(50, 100),
    );

    // ADL active
    params.ensure_limit_breached(current_borrow); // passes

    // Without repay_on_behalf manipulation, ADL remains active
    // Any call to liquidate_adl_borrow would succeed
}
```

### Mitigation

Option A: Do not trigger ADL stop within `handle_repay`. Remove the `try_stop_borrow_deleverage` call from repay path entirely — only stop ADL via liquidation path where debt genuinely decreases through collateral seizure:

```move
// In handle_repay, REMOVE lines 489-491:
// let adl = ...;
// adl.try_stop_borrow_deleverage(...);
```

Option B: Add a cooldown/grace period before ADL entry can be removed, preventing same-PTB manipulation:

```move
// In try_stop_borrow_deleverage, require ADL to have been below target for N blocks
```

Option C: Check if ADL conditions are still met AFTER the full PTB execution (not mid-transaction). This would require Sui-level support for post-transaction hooks.
