# Flash Loan Withdraw Does Not Update `cash` Field, Causing Stale Reserve State Within PTB

## Summary

`flash_loan_withdraw` in `reserve.move` withdraws tokens from `underlying_balance` but does not decrement `self.cash`. During the flash loan window within a PTB (Programmable Transaction Block), other composable operations see inflated `cash` values, leading to incorrect exchange rates, utilization rates, and borrow availability checks.

## Vulnerability Detail

In `reserve.move:318-324`, `flash_loan_withdraw` only splits the balance without updating accounting:

```move
fun flash_loan_withdraw<MarketType, CoinType>(
    self: &mut Reserve<MarketType>,
    amount: u64,
): Balance<CoinType> {
    let reserve_token_balance: &mut ReserveBalance<MarketType, CoinType> = dynamic_field::borrow_mut(&mut self.id, ReserveBalanceKey{});
    reserve_token_balance.underlying_balance.split(amount)
}
```

Compare with the normal `withdraw_underlying` (line 306-316), which correctly updates `self.cash`:

```move
fun withdraw_underlying<MarketType, CoinType>(
    self: &mut Reserve<MarketType>,
    amount: u64,
): Balance<CoinType> {
    let reserve_token_balance: &mut ReserveBalance<MarketType, CoinType> = dynamic_field::borrow_mut(&mut self.id, ReserveBalanceKey{});
    self.cash = self.cash - amount;
    assert!(self.cash >= self.cash_reserve.ceil(), error::market_cash_reserve_not_enough());
    reserve_token_balance.underlying_balance.split(amount)
}
```

During the flash loan window (between `borrow_flash_loan` and `repay_flash_loan` within the same PTB), the following reserve properties are incorrect:

1. **`exchange_rate()`** — inflated (uses `self.cash` in numerator of `cash_plus_borrows_minus_reserves`)
2. **`util_rate()`** — deflated (inflated denominator)
3. **`borrow_amount()`** check — passes with more headroom than actually available (`self.cash - self.cash_reserve.ceil() > amount`)
4. **`deposit_limit_breached()`** — calculates higher total deposit than reality

## Internal Pre-conditions

1. A flash loan must be active within a PTB (between `borrow_flash_loan` and `repay_flash_loan`).
2. Other market operations must be composed with the flash loan in the same PTB.

## External Pre-conditions

None.

## Attack Path

1. `PackageCallerCap` holder (whitelisted contract) composes a flash loan with other operations in a single PTB.
2. `borrow_flash_loan` withdraws tokens from `underlying_balance` but does NOT update `self.cash`.
3. A deposit operation within the same PTB sees inflated `exchange_rate` (cash is overstated).
4. The depositor receives fewer cTokens than warranted for their deposit amount.
5. When the flash loan is repaid, cash is restored, but the depositor has already been shortchanged.

## Impact

In Sui's PTB model, multiple operations can be composed within a single transaction. If a flash loan is composed with other market operations (via whitelisted `PackageCallerCap` holders), the intermediate state is inconsistent:

- A deposit during the flash loan window would see an inflated exchange rate, minting fewer cTokens for the same deposit amount (user receives less value)
- A borrow check during the flash loan window would see `cash` as available when the actual `underlying_balance` has been depleted, potentially allowing a borrow that fails at the balance level with a low-level abort instead of the intended `reserve_not_enough_error`
- Interest accrual during the window would compute incorrect utilization rate, leading to a lower interest rate than market conditions warrant

The test at line 785-789 confirms this behavior — `reserve.cash` remains at 1000 after flash-borrowing 100:
```move
let (borrowed_balance, loan) = reserve.borrow_flash_loan<MainMarket, BTC>(100);
assert!(reserve.cash == 1000);  // cash not updated!
```

## Code Snippet

- `reserve.move:318-324` — `flash_loan_withdraw` (does NOT update `self.cash`)
- `reserve.move:306-316` — `withdraw_underlying` (correctly updates `self.cash`)
- `reserve.move:92-101` — `exchange_rate` (uses stale `self.cash`)
- `reserve.move:65-72` — `util_rate` (uses stale `self.cash`)

## Tool used

Manual Review + Automated Analysis

## Mitigation

Update `self.cash` in `flash_loan_withdraw` and restore it in `repay_flash_loan`:

```move
fun flash_loan_withdraw<MarketType, CoinType>(
    self: &mut Reserve<MarketType>,
    amount: u64,
): Balance<CoinType> {
    let reserve_token_balance: &mut ReserveBalance<MarketType, CoinType> = dynamic_field::borrow_mut(&mut self.id, ReserveBalanceKey{});
    self.cash = self.cash - amount;  // keep cash in sync
    reserve_token_balance.underlying_balance.split(amount)
}
```

And in `repay_flash_loan`, add `self.cash = self.cash + coin.value()` before restoring the balance.
