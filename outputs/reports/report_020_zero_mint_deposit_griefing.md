# Zero-Mint Deposit Griefing via Truncating Division

## Summary

When the cToken exchange rate is high enough (due to accumulated interest), small deposits can result in zero cTokens minted due to truncating integer division in `int_mul`. The depositor's tokens are absorbed into the reserve but they receive nothing in return, effectively donating their deposit.

## Vulnerability Detail

The cToken minting calculation uses `int_mul` which performs floor division:

```move
// In reserve handling, mint amount = deposit / exchange_rate
// exchange_rate = (cash + borrows - reserves) / total_supply
// mint = deposit_amount * total_supply / (cash + borrows - reserves)
```

When `exchange_rate` is high (e.g., after significant interest accrual) and `deposit_amount` is small:
```
mint_amount = int_mul(inverse_exchange_rate, deposit_amount)
            = (inverse_rate.value * deposit_amount) / WAD
            = 0  (if product < WAD)
```

The depositor's tokens are added to the reserve's cash balance, but zero cTokens are minted. The deposit is effectively distributed pro-rata to existing cToken holders via the improved exchange rate.

There is no minimum deposit check or zero-mint revert in the deposit flow.

## Impact

- **Silent fund loss**: Users making small deposits (relative to the exchange rate) lose their tokens with no cTokens received
- **Griefing vector**: An attacker can donate small amounts to inflate the exchange rate, then subsequent small depositors lose funds
- **First-depositor inflation variant**: While not a classic first-depositor attack (the protocol may have safeguards for initial deposits), the exchange rate drift over time creates the same effect for latecomers

## Code Snippet

- [`float.move:63-65`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/math/sources/float.move#L63-L65): `int_mul` truncating division
- [`reserve.move`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move): cToken mint calculation

## Tool used

Manual Review + Automated Analysis (Codex + Claude cross-validation)

## Recommendation

Revert if zero cTokens would be minted:

```move
let mint_amount = calculate_mint(deposit_amount, exchange_rate);
assert!(mint_amount > 0, error::deposit_too_small());
```
