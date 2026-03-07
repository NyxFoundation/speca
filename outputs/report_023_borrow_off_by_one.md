# Borrow Off-By-One Liquidity Lock

## Summary

The borrow amount validation in `reserve.move` uses strict greater-than (`>`) instead of greater-than-or-equal (`>=`), preventing users from borrowing the exact remaining available liquidity. This locks 1 unit of each asset permanently in the reserve until new deposits arrive.

## Vulnerability Detail

In `reserve.move:196-201`:

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

Available liquidity is `cash - ceil(cash_reserve)`. If this equals 100, a user trying to borrow exactly 100 will fail because `100 > 100` is false. They can only borrow 99.

The same pattern exists in flash loans (line 230):
```move
assert!(amount < self.cash, error::reserve_flash_loan_more_than_cash());
```

## Impact

- **Capital inefficiency**: 1 unit per asset per reserve is permanently locked and unusable
- **User confusion**: Borrowers see available liquidity but cannot borrow the full amount
- **Compounding effect**: Across many assets and markets, the locked amounts aggregate

The severity is low per-asset but is a correctness issue in the liquidity model.

## Code Snippet

- [`reserve.move:199`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L199): Strict `>` check
- [`reserve.move:230`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L230): Same pattern in flash loan

## Tool used

Manual Review + Automated Analysis (Codex + Claude cross-validation)

## Recommendation

Use `>=` for exact-amount borrowing:

```move
assert!(self.cash - self.cash_reserve.ceil() >= amount, error::reserve_not_enough_error());
```
