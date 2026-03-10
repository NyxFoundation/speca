### Flash Loan Withdraw Does Not Update `cash` Field, Causing Stale Reserve State Within PTB

A whitelisted contract composing flash loans with other market operations will cause depositors to receive fewer cTokens than warranted due to inflated exchange rates during the flash loan window

### Summary

`flash_loan_withdraw` in `reserve.move` withdraws tokens from `underlying_balance` but does not decrement `self.cash` will cause an incorrect exchange rate, utilization rate, and borrow availability for depositors and borrowers as a whitelisted `PackageCallerCap` holder will compose a flash loan with other market operations in a single PTB, where the inflated `cash` value produces stale reserve state during the flash loan window

### Root Cause

In [`reserve.move:318-324`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L318-L324) the `flash_loan_withdraw` function only splits the balance without updating `self.cash`:

```move
fun flash_loan_withdraw<MarketType, CoinType>(
    self: &mut Reserve<MarketType>,
    amount: u64,
): Balance<CoinType> {
    let reserve_token_balance: &mut ReserveBalance<MarketType, CoinType> = dynamic_field::borrow_mut(&mut self.id, ReserveBalanceKey{});
    reserve_token_balance.underlying_balance.split(amount)
}
```

Compare with the normal `withdraw_underlying` ([`reserve.move:306-316`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L306-L316)), which correctly updates `self.cash`:

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

During the flash loan window, the following reserve properties are incorrect:
1. `exchange_rate()` ([`reserve.move:92-101`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L92-L101)) -- inflated (uses `self.cash` in numerator of `cash_plus_borrows_minus_reserves`)
2. `util_rate()` ([`reserve.move:65-72`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L65-L72)) -- deflated (inflated denominator)
3. `borrow_amount()` check -- passes with more headroom than actually available
4. `deposit_limit_breached()` -- calculates higher total deposit than reality

The existing test at line 785-789 confirms this behavior:
```move
let (borrowed_balance, loan) = reserve.borrow_flash_loan<MainMarket, BTC>(100);
assert!(reserve.cash == 1000);  // cash not updated!
```

### Internal Pre-conditions

1. [A whitelisted contract needs to call `borrow_flash_loan` to set] a flash loan to be active within a PTB
2. [The same PTB needs to compose additional market operations to set] other operations to execute while `cash` is stale

### External Pre-conditions

None.

### Attack Path

1. `PackageCallerCap` holder (whitelisted contract) composes a flash loan with other operations in a single PTB.
2. `borrow_flash_loan` withdraws tokens from `underlying_balance` but does NOT update `self.cash`.
3. A deposit operation within the same PTB sees inflated `exchange_rate` (cash is overstated).
4. The depositor receives fewer cTokens than warranted for their deposit amount.
5. When the flash loan is repaid, cash is restored, but the depositor has already been shortchanged.

### Impact

The depositors suffer a loss of cToken value proportional to the flash loan amount relative to total reserves. A deposit during the flash loan window sees an inflated exchange rate, minting fewer cTokens for the same deposit amount. A borrow check during the window sees `cash` as available when the actual `underlying_balance` has been depleted, potentially allowing a borrow that fails at the balance level with a low-level abort instead of the intended `reserve_not_enough_error`. Interest accrual during the window computes incorrect utilization rate, leading to a lower interest rate than market conditions warrant.

### PoC

No standalone PoC is possible due to PTB (Programmable Transaction Block) composition limitations in the test framework. Below is a detailed code walkthrough showing the bug path:

1. **`flash_loan_withdraw` does not update `cash`** (`reserve.move:318-324`):
   ```move
   fun flash_loan_withdraw<MarketType, CoinType>(
       self: &mut Reserve<MarketType>,
       amount: u64,
   ): Balance<CoinType> {
       let reserve_token_balance: &mut ReserveBalance<MarketType, CoinType> =
           dynamic_field::borrow_mut(&mut self.id, ReserveBalanceKey{});
       reserve_token_balance.underlying_balance.split(amount)
       // NOTE: self.cash is NOT decremented here
   }
   ```

2. **`exchange_rate` uses stale `self.cash`** (`reserve.move:92-101`):
   ```move
   public(package) fun exchange_rate<MarketType>(self: &Reserve<MarketType>): Decimal {
       // cash_plus_borrows_minus_reserves uses self.cash
       // After flash_loan_withdraw: self.cash is inflated by `amount`
       // → exchange_rate is inflated
   }
   ```

3. **Deposit during flash loan window** receives fewer cTokens:
   - `exchange_rate` is inflated because `self.cash` is higher than actual balance
   - `cTokens_minted = deposit_amount / exchange_rate`
   - Higher exchange rate -> fewer cTokens for the same deposit

4. **Existing test confirms the bug** (`reserve.move:785-789`):
   ```move
   let (borrowed_balance, loan) = reserve.borrow_flash_loan<MainMarket, BTC>(100);
   assert!(reserve.cash == 1000);  // cash NOT updated after withdrawing 100
   ```

### Mitigation

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
