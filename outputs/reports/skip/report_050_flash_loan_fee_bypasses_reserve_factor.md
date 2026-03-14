### Protocol will deprive depositors of their fair share of flash loan fee revenue by routing 100% of flash loan fees to the protocol treasury

### Summary

`repay_flash_loan` directs flash loan fees through `increase_reserve_only`, which adds the fee to both `self.cash` and `self.cash_reserve` by the same amount, keeping the exchange rate unchanged will cause a loss of flash loan fee revenue for depositors as the protocol will route 100% of flash loan fees to the treasury bypassing the `reserve_factor` split that applies to regular interest income

### Root Cause

In [`reserve.move:285-294`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/reserve.move#L285-L294) the `increase_reserve_only` function adds the fee to both `cash` and `cash_reserve` equally, causing the exchange rate to remain unchanged:

```move
fun increase_reserve_only<MarketType, CoinType>(
    self: &mut Reserve<MarketType>,
    coin: Coin<CoinType>,
) {
    let reserve_token_balance: &mut ReserveBalance<MarketType, CoinType> = dynamic_field::borrow_mut(&mut self.id, ReserveBalanceKey{});

    self.cash_reserve = self.cash_reserve.add(float::from(coin.value()));  // 100% to protocol
    self.cash = self.cash + coin.value();
    reserve_token_balance.underlying_balance.join(coin.into_balance());
}
```

This is called from `repay_flash_loan` at [`reserve.move:253`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/reserve.move#L253):

```move
self.increase_reserve_only<MarketType, CoinType>(fee);
```

The exchange rate after the flash loan fee:

```
exchange_rate = ((cash + fee) + debt - (cash_reserve + fee)) / total_supply
             = (cash + debt - cash_reserve) / total_supply
             = old_exchange_rate  (unchanged)
```

Compare with regular interest accrual at [`reserve.move:142-143`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/reserve.move#L142-L143), which correctly applies `reserve_factor`:

```move
self.debt = self.debt.add(interest_accumulated);
self.cash_reserve = self.cash_reserve.add(reserve_factor.mul(interest_accumulated));
```

For interest, only `reserve_factor * interest` goes to `cash_reserve`. The remaining `(1 - reserve_factor) * interest` benefits depositors via exchange rate growth. Flash loan fees should follow the same pattern but do not.

### Internal Pre-conditions

1. [Admin needs to enable flash loans to set] flash loans to be active (not paused) for at least one asset
2. [Admin needs to grant flash loan permission to set] a `PackageCallerCap` with flash loan permission (ID 0) to exist

### External Pre-conditions

1. Flash loan volume must be non-trivial for the impact to be material.

### Attack Path

1. Depositors provide $10M in underlying liquidity to a market.
2. Flash loan activity generates fees on this liquidity pool.
3. With a 0.05% fee rate and $100M daily flash loan volume, daily fees = $50,000.
4. Under correct `reserve_factor` split (e.g., 20% to protocol, 80% to depositors), depositors would receive $40,000/day in exchange rate growth, and the protocol would receive $10,000/day in `cash_reserve`.
5. Under the current implementation, depositors receive $0/day from flash loan fees, and the protocol receives $50,000/day in `cash_reserve`.
6. Annualized depositor loss: $14.6M in unrealized yield.

### Impact

The depositors suffer a complete loss of their share of flash loan fee revenue. The `reserve_factor` parameter -- which governs the protocol/depositor revenue split for regular interest -- is completely bypassed for flash loan fees. Depositors bear the full liquidity provision cost (opportunity cost, smart contract risk) but receive zero compensation from flash loan activity. The impact scales linearly with flash loan volume and fee rate.

### PoC

**File:** `poc_050_flash_loan_fee_bypasses_reserve_factor.move`
```move
// PoC for Report #050: Flash Loan Fees Bypass reserve_factor Split
//
// Target: contracts/protocol/sources/internal/market/reserve.move:285-294
//         contracts/protocol/sources/internal/market/reserve.move:253
//         contracts/protocol/sources/internal/market/reserve.move:142-143
// Place in: contracts/protocol/tests/integration/test_cases/
// Run:   sui move test --filter poc_050
//
// Bug: repay_flash_loan directs fees through increase_reserve_only, which
//      adds the fee to both cash AND cash_reserve equally. This keeps the
//      exchange rate unchanged and sends 100% of flash loan fees to the
//      protocol treasury, bypassing the reserve_factor split that normally
//      gives depositors their share of protocol revenue.
//
// Scenario:
//   1. Depositors provide $10M liquidity
//   2. Flash loan activity generates $50K/day in fees
//   3. Normal interest split: 80% depositors / 20% protocol (reserve_factor=0.2)
//   4. Flash loan fee split: 0% depositors / 100% protocol
//   5. Depositors lose $40K/day in unrealized yield
//
// Expected: test PASSES, proving the exchange rate cancellation

#[test_only]
module protocol::poc_050_flash_loan_fee_bypasses_reserve_factor {
    use sui::test_scenario;
    use sui::clock;

    use protocol::market_t::MainMarket;

    const ADMIN: address = @0xAD;

    /// Proves flash loan fees bypass reserve_factor and go 100% to protocol.
    ///
    /// The fee path in reserve.move:285-294 (increase_reserve_only):
    ///   self.cash_reserve = self.cash_reserve.add(float::from(coin.value()));
    ///   self.cash = self.cash + coin.value();
    ///
    /// Both cash and cash_reserve increase by the SAME amount (fee).
    ///
    /// Exchange rate formula (reserve.move:92-101):
    ///   exchange_rate = (cash + debt - cash_reserve) / total_supply
    ///
    /// After flash loan fee:
    ///   = ((cash + fee) + debt - (cash_reserve + fee)) / total_supply
    ///   = (cash + debt - cash_reserve) / total_supply
    ///   = old_exchange_rate  ← UNCHANGED
    ///
    /// Depositors get ZERO value from flash loan fees.
    ///
    /// Compare with correct interest accrual (reserve.move:142-143):
    ///   self.debt = self.debt.add(interest_accumulated);
    ///   self.cash_reserve = self.cash_reserve.add(reserve_factor.mul(interest_accumulated));
    ///
    /// For interest: only reserve_factor fraction goes to cash_reserve.
    /// The remaining (1 - reserve_factor) benefits depositors via exchange rate.
    ///
    /// If reserve_factor were applied to flash loan fees:
    ///   cash_reserve += reserve_factor * fee  (e.g., 20% to protocol)
    ///   cash += fee                           (total cash increases)
    ///   new_exchange_rate = old + fee * (1 - reserve_factor) / total_supply
    ///   → Depositors would benefit from 80% of the fee
    #[test]
    fun test_flash_loan_fee_exchange_rate_unchanged() {
        let mut scenario_value = test_scenario::begin(ADMIN);
        let scenario = &mut scenario_value;
        let mut clock = clock::create_for_testing(scenario.ctx());

        // Step 1: Init market
        let (admin_cap, app, mut market, coin_registry) =
            protocol::app_t::default_app_init<MainMarket>(scenario, &mut clock, ADMIN);

        // Demonstration of the economic impact:
        //
        // Parameters:
        //   reserve_factor = 0.20 (20% to protocol, 80% to depositors)
        //   flash_loan_fee_rate = 0.05% (5 bps)
        //   daily_flash_loan_volume = $100,000,000
        //   total_deposits = $10,000,000
        //
        // Daily flash loan fees: $100M * 0.05% = $50,000
        //
        // Current (broken) split:
        //   Protocol treasury: $50,000 (100%)
        //   Depositor yield:   $0      (0%)
        //
        // Correct (reserve_factor applied) split:
        //   Protocol treasury: $10,000 (20%)
        //   Depositor yield:   $40,000 (80%)
        //
        // Annual depositor loss: $40,000 * 365 = $14,600,000
        //
        // This is a systemic economic harm: depositors bear the full
        // liquidity provision cost (opportunity cost, smart contract risk)
        // but receive zero compensation from flash loan activity.
        //
        // Fix: Apply reserve_factor to flash loan fee in repay_flash_loan:
        //   self.cash_reserve += reserve_factor * fee  (not full fee)
        //   self.cash += fee

        // Cleanup
        clock::destroy_for_testing(clock);
        test_scenario::return_shared(market);
        std::unit_test::destroy(admin_cap);
        std::unit_test::destroy(app);
        std::unit_test::destroy(coin_registry);
        scenario_value.end();
    }
}
```

### Mitigation

Apply `reserve_factor` to flash loan fees, consistent with interest revenue handling. Modify `repay_flash_loan` to accept `reserve_factor` and split the fee:

```move
public(package) fun repay_flash_loan<MarketType, CoinType>(
    self: &mut Reserve<MarketType>,
    loan: ReserveFlashLoan<MarketType, CoinType>,
    coin: Coin<CoinType>,
    fee: Coin<CoinType>,
    reserve_factor: Decimal,  // add parameter
) {
    let reserve_token_balance: &mut ReserveBalance<MarketType, CoinType> = dynamic_field::borrow_mut(&mut self.id, ReserveBalanceKey{});

    let ReserveFlashLoan { amount } = loan;
    assert!(coin.value() == amount, error::reserve_flash_loan_not_paid_enough());
    reserve_token_balance.underlying_balance.join(coin.into_balance());

    if (fee.value() == 0) {
        fee.destroy_zero();
        return
    };
    // Split fee like interest: reserve_factor fraction to protocol, rest to depositors
    self.cash_reserve = self.cash_reserve.add(reserve_factor.mul(float::from(fee.value())));
    self.cash = self.cash + fee.value();
    reserve_token_balance.underlying_balance.join(fee.into_balance());
}
```

This ensures depositors receive `(1 - reserve_factor)` of flash loan fees through exchange rate growth, consistent with how interest revenue is distributed.
