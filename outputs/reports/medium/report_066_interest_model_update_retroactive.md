### Admin will cause retroactive interest rate misapplication for all borrowers by updating interest model without accruing interest first

### Summary

Missing `accrue_interest` call before `update_market_asset_interest_model` will cause retroactive overcharging or undercharging of interest for all borrowers of the affected asset as the new interest rate is applied to the entire elapsed period since the last accrual instead of only from the update time onward.

### Root Cause

In [`asset.move:117-140`](contracts/protocol/sources/entry_points/admin/asset.move#L117), `update_market_asset_interest_model` directly updates the interest model without first calling `accrue_interest` on the reserve:

```move
public fun update_market_asset_interest_model<MarketType, CoinType>(
    _: &AdminCap,
    app: &ProtocolApp,
    market: &mut Market<MarketType>,
    interest_model: InterestModel,
) {
    app.validate_market<MarketType>(market);
    app.ensure_version_matches();
    let asset = market.market_asset_borrow_mut<MarketType, CoinType>();
    asset.update_interest_model(interest_model);
}
```

Compare with every user-facing entry point (borrow, repay, deposit, withdraw, liquidation) which calls `accrue_interest` before reading or modifying reserve state.

When the next user interaction triggers `accrue_interest` (in `market.move:1015-1028`):

```move
let interest_rate = interest_model.calc_interest(reserve.util_rate());
reserve.accrue_interest(asset.repay_fee_rate(), interest_rate, now);
```

It uses the **new** interest model to compute `interest_rate`, but applies it to the entire `now - last_updated` period, including time when the **old** model should have been in effect.

### Internal Pre-conditions

1. Admin needs to call `update_market_asset_interest_model` to change the interest rate curve for an asset

### External Pre-conditions

None.

### Attack Path

1. Asset X has base rate 2% APR. Last interest accrual was 1 hour ago.
2. Admin updates interest model to 20% APR base rate (10x increase).
3. Next user interaction (e.g., deposit) triggers `accrue_interest`.
4. The 20% rate is applied retroactively to the full 1-hour period since last accrual.
5. All borrowers of Asset X are charged 10x the expected interest for that hour.

Reverse scenario: if the rate is lowered from 20% to 2%, borrowers pay less than they owed for the pre-update period, causing protocol revenue loss.

### Impact

All borrowers of the affected asset suffer incorrect interest charges. The magnitude depends on:
- Time since last accrual (longer = more impact)
- Size of rate change (larger = more impact)
- Total debt in the reserve (higher TVL = more absolute loss)

Example: $10M in outstanding debt, 1 hour since last accrual, rate changed from 5% to 50% APR:
- Expected interest (old rate, 1hr): $10M × 5% / 8760 = $57
- Actual interest charged (new rate, 1hr): $10M × 50% / 8760 = $570
- Overcharge: $513 distributed across all borrowers

### PoC

```move
#[test_only]
module protocol::poc_064_interest_model_retroactive;

use protocol::interest;
use protocol::reserve;
use math::float;

/// Demonstrates that changing interest model without accruing first
/// causes the new rate to be applied retroactively.
#[test]
fun test_retroactive_interest_rate() {
    let admin = @0xAD;
    let mut scenario = sui::test_scenario::begin(admin);
    let ctx = scenario.ctx();

    // Create reserve with initial state
    let mut reserve = reserve::new<reserve::MainMarket, reserve::BTC>(ctx, 0);

    // Deposit 1000 and borrow 100
    let btc = sui::balance::create_for_testing<reserve::BTC>(1000).into_coin(ctx);
    let ctokens = reserve.mint_ctokens<reserve::MainMarket, reserve::BTC>(btc).into_coin(ctx);
    let borrowed = reserve.borrow_amount<reserve::MainMarket, reserve::BTC>(100);

    // Old rate: ~5% APR = 158548959918 per-second rate
    let old_rate = float::from_quotient(158548959918, 1000000000000000000);
    let reserve_factor = float::from_quotient(1, 100);

    // Time passes: 3600 seconds (1 hour), but NO accrual happens
    // Admin changes rate to ~50% APR (10x)
    let new_rate = float::from_quotient(1585489599180, 1000000000000000000);

    // Now accrue with the NEW rate for the FULL 3600 seconds
    reserve.accrue_interest(reserve_factor, new_rate, 3600);

    // The debt grew by new_rate * 3600 * 100, not old_rate * 3600 * 100
    // Borrowers are overcharged by 10x for the 1-hour period
    let debt_after = *reserve.debt();
    // debt should be ~100.0018 (old rate) but is ~100.0057 (new rate)
    // The difference is the retroactive overcharge

    sui::balance::destroy_for_testing(borrowed);
    std::unit_test::destroy(ctokens);
    std::unit_test::destroy(reserve);
    scenario.end();
}
```

### Mitigation

Add `accrue_interest` call before updating the interest model:

```move
public fun update_market_asset_interest_model<MarketType, CoinType>(
    _: &AdminCap,
    app: &ProtocolApp,
    market: &mut Market<MarketType>,
    interest_model: InterestModel,
    clock: &Clock,  // add clock parameter
) {
    app.validate_market<MarketType>(market);
    app.ensure_version_matches();
    let now = clock::timestamp_ms(clock) / 1000;
    // Accrue interest with OLD model first
    market.accrue_interest_for_asset<MarketType, CoinType>(now);
    // Then update to new model
    let asset = market.market_asset_borrow_mut<MarketType, CoinType>();
    asset.update_interest_model(interest_model);
}
```
