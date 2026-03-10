### Borrower will be unable to borrow exact remaining available liquidity, locking 1 unit per asset in the reserve

### Summary

Off-by-one error in the borrow amount validation (strict `>` instead of `>=`) will cause capital inefficiency for borrowers as the protocol will reject borrows equal to the exact remaining available liquidity, permanently locking 1 unit per asset per reserve.

### Root Cause

In [`reserve.move:199`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L199) the borrow amount check uses strict greater-than instead of greater-than-or-equal:

```move
public(package) fun borrow_amount<MarketType, CoinType>(
    self: &mut Reserve<MarketType>, amount: u64
): Balance<CoinType> {
    assert!(self.cash - self.cash_reserve.ceil() > amount, error::reserve_not_enough_error());
    //                                          ^^^ strict > instead of >=
    self.debt = self.debt.add_u64(amount);
    self.withdraw_underlying(amount)
}
```

The same pattern exists in flash loans ([`reserve.move:230`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L230)):
```move
assert!(amount < self.cash, error::reserve_flash_loan_more_than_cash());
```

### Internal Pre-conditions

1. [Depositors need to deposit funds to set] available liquidity (`cash - ceil(cash_reserve)`) to be exactly equal to the desired borrow amount.

### External Pre-conditions

None.

### Attack Path

1. Reserve has exactly 100 units of available liquidity.
2. User calls `borrow_amount` with `amount = 100`.
3. `assert!(100 > 100)` fails, transaction aborts.
4. User can only borrow 99, leaving 1 unit locked.

### Impact

The borrowers suffer an approximate loss of 1 unit per asset per reserve in locked, unusable liquidity. Across many assets and markets, the locked amounts aggregate. Borrowers see available liquidity but cannot borrow the full amount.

### PoC

_No PoC provided._

### Mitigation

Use `>=` for exact-amount borrowing:

```move
assert!(self.cash - self.cash_reserve.ceil() >= amount, error::reserve_not_enough_error());
```
