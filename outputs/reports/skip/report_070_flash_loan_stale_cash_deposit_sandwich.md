# H-070: Flash Loan Creates `reserve.cash` / `underlying_balance` Invariant Violation

## Severity
Medium (downgraded from initial High assessment)

## Summary
When a flash loan is taken via `reserve::borrow_flash_loan`, the `flash_loan_withdraw` function removes tokens from `underlying_balance` but does NOT update `reserve.cash`. This creates a state inconsistency where `reserve.cash != underlying_balance.value()` during the flash loan window. While the `flash_loan_lock` prevents re-entrant flash loans on the same asset, other operations (deposit, borrow, withdraw, repay, liquidation) are NOT blocked and may operate against stale state.

## Root Cause

In `reserve.move`, `flash_loan_withdraw` (lines 318-324) only splits from `underlying_balance` without updating `self.cash`:

```move
fun flash_loan_withdraw<MarketType, CoinType>(
    self: &mut Reserve<MarketType>,
    amount: u64,
): Balance<CoinType> {
    let reserve_token_balance: &mut ReserveBalance<MarketType, CoinType> =
        dynamic_field::borrow_mut(&mut self.id, ReserveBalanceKey{});
    reserve_token_balance.underlying_balance.split(amount)
    // NOTE: self.cash is NOT decremented
}
```

Similarly, `repay_flash_loan` (lines 234-254) joins the principal back to `underlying_balance` without updating `self.cash` for the principal (only the fee updates `self.cash` via `increase_reserve_only`).

The net effect is that `self.cash` and `underlying_balance.value()` are in sync before and after the complete flash loan cycle, but they diverge DURING the flash loan.

## Impact Analysis

### What IS affected during a flash loan:

1. **`borrow_amount()` check (reserve.move line 197)**: `assert!(self.cash - self.cash_reserve.ceil() > amount)` uses the stale (inflated) `self.cash`. This check could PASS for amounts up to `original_cash - cash_reserve`, even though `underlying_balance` only has `original_cash - flash_loan_amount` tokens. However, the subsequent `withdraw_underlying(amount)` would ABORT when trying to split more than available from `underlying_balance`. So the attack does not succeed; the transaction reverts.

2. **`util_rate()` (reserve.move line 65-72)**: Computed as `debt / (cash + debt - cash_reserve)` with stale `cash`, resulting in an artificially LOW utilization rate. Within a single Sui PTB, interest accrual is idempotent (skips if `last_updated == now`), so this doesn't lead to under-accrual in practice.

3. **`deposit_limit_breached()` (reserve.move line 87-90)**: Uses `exchange_rate()` which depends on stale `cash`. The exchange rate = `(cash + debt - cash_reserve) / total_supply`. Since `cash` is not decremented, the exchange rate is the SAME as pre-flash-loan, so deposits see the normal limit check.

### What is NOT affected:

- **`exchange_rate()`**: Since `self.cash` is NOT decremented during the flash loan, and `total_supply`, `debt`, and `cash_reserve` are unchanged, the exchange rate remains the same. This means the deposit sandwich attack described in the initial assessment does NOT work.

- **`is_obligation_safe`**: Uses exchange rates which are unaffected.

## Actual Risk

The primary risk is that the invariant `self.cash == underlying_balance.value()` is violated during the flash loan window. In the current codebase, this is mitigated by:

1. `underlying_balance.split()` aborting on insufficient balance (preventing actual fund extraction)
2. Interest accrual being idempotent within the same timestamp
3. Exchange rate not being affected (because `self.cash` stays the same)

However, this invariant violation is a latent risk: any future code that relies on `self.cash` accurately reflecting the actual token balance could introduce a vulnerability.

## Affected Code

- `reserve.move` lines 318-324 (`flash_loan_withdraw`)
- `reserve.move` lines 225-232 (`borrow_flash_loan`)
- `reserve.move` lines 234-254 (`repay_flash_loan`)

## Recommendation

Update `flash_loan_withdraw` to decrement `self.cash` and update the principal repayment in `repay_flash_loan` to re-increment it:

```move
fun flash_loan_withdraw<MarketType, CoinType>(
    self: &mut Reserve<MarketType>,
    amount: u64,
): Balance<CoinType> {
    self.cash = self.cash - amount;
    let reserve_token_balance = ...;
    reserve_token_balance.underlying_balance.split(amount)
}
```

And in `repay_flash_loan`:
```move
self.cash = self.cash + coin.value();
reserve_token_balance.underlying_balance.join(coin.into_balance());
```

This maintains the `self.cash == underlying_balance.value()` invariant at all times.
