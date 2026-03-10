# Flash Loan Fees Bypass `reserve_factor` Split and Go Entirely to Protocol, Depriving Depositors of Fee Revenue

## Summary

`repay_flash_loan` directs flash loan fees through `increase_reserve_only`, which adds the fee to both `self.cash` and `self.cash_reserve` by the same amount. This keeps the exchange rate unchanged and sends 100% of flash loan fee revenue to the protocol treasury, bypassing the `reserve_factor` split that applies to regular interest income. Depositors — who provide all the underlying liquidity enabling flash loans — receive zero share of flash loan fees.

## Vulnerability Detail

In `reserve.move:125-149`, regular interest revenue is split between protocol and depositors using `reserve_factor`:

```move
// reserve.move:142-143 (interest accrual)
self.debt = self.debt.add(interest_accumulated);
self.cash_reserve = self.cash_reserve.add(reserve_factor.mul(interest_accumulated));
```

Only `reserve_factor * interest_accumulated` is added to `cash_reserve` (protocol revenue). The remaining `(1 - reserve_factor) * interest_accumulated` benefits depositors through exchange rate growth, since `exchange_rate = (cash + debt - cash_reserve) / total_supply` — debt increases by the full interest but `cash_reserve` only increases by the `reserve_factor` fraction.

However, flash loan fees follow a completely different path. In `repay_flash_loan` (reserve.move:234-254), the fee coin is processed via `increase_reserve_only`:

```move
// reserve.move:253
self.increase_reserve_only<MarketType, CoinType>(fee);
```

Which does:

```move
// reserve.move:285-294
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

Both `cash` and `cash_reserve` increase by the same amount (`fee`). The exchange rate after the flash loan fee:

```
exchange_rate = ((cash + fee) + debt - (cash_reserve + fee)) / total_supply
             = (cash + debt - cash_reserve) / total_supply
             = old_exchange_rate  (unchanged)
```

Depositors receive zero value from flash loan fees. The entire fee goes to `cash_reserve` (protocol treasury, extractable via `take_revenue`).

Compare this with how the fee SHOULD be processed (consistent with interest accrual):

```
// If reserve_factor were applied:
cash_reserve += reserve_factor * fee   (protocol gets reserve_factor fraction)
cash += fee                            (total cash increases)

// New exchange rate:
exchange_rate = ((cash + fee) + debt - (cash_reserve + reserve_factor * fee)) / total_supply
             = old_exchange_rate + fee * (1 - reserve_factor) / total_supply
```

Depositors would benefit from `(1 - reserve_factor) * fee` through exchange rate growth.

## Internal Pre-conditions

1. Flash loans must be active (not paused) for at least one asset.
2. A `PackageCallerCap` with flash loan permission (ID 0) must exist.

## External Pre-conditions

1. Flash loan volume must be non-trivial for the impact to be material.

## Attack Path

This is not an active attack but a systemic economic harm to depositors:

1. Depositors provide $10M in underlying liquidity to a market.
2. Flash loan activity generates fees on this liquidity pool.
3. With a 0.05% fee rate and $100M daily flash loan volume, daily fees = $50,000.
4. Under correct `reserve_factor` split (e.g., 20% to protocol, 80% to depositors):
   - Depositors would receive $40,000/day in exchange rate growth.
   - Protocol would receive $10,000/day in `cash_reserve`.
5. Under the current implementation:
   - Depositors receive $0/day from flash loan fees.
   - Protocol receives $50,000/day in `cash_reserve`.
6. Annualized depositor loss: $14.6M in unrealized yield.

## Impact

All depositors are systematically deprived of their fair share of flash loan fee revenue. The `reserve_factor` parameter — which governs the protocol/depositor revenue split for regular interest — is completely bypassed for flash loan fees. This creates an economic asymmetry where depositors bear the liquidity provision cost (opportunity cost, smart contract risk) but receive zero compensation from flash loan activity.

The impact scales linearly with flash loan volume and fee rate. In mature DeFi lending protocols, flash loan fees can represent a significant revenue stream (comparable to or exceeding interest income during high-volatility periods).

## Code Snippet

- [`reserve.move:285-294`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/reserve.move#L285-L294): `increase_reserve_only` — adds fee to both `cash` and `cash_reserve`, keeping exchange rate unchanged
- [`reserve.move:142-143`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/reserve.move#L142-L143): `accrue_interest` — correctly applies `reserve_factor` to split revenue
- [`reserve.move:253`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/reserve.move#L253): `repay_flash_loan` calls `increase_reserve_only` for the fee
- [`reserve.move:92-101`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/market/reserve.move#L92-L101): `exchange_rate` — demonstrates the cancellation effect

## Tool used

Manual Review + Automated Analysis

## Recommendation

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
