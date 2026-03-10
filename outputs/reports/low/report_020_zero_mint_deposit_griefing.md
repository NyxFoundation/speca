### Zero-Mint Deposit Griefing via Truncating Division

Depositor will lose funds by receiving zero cTokens when depositing small amounts at a high exchange rate

### Summary

Truncating integer division in `int_mul` with no minimum mint check will cause a silent loss of deposited funds for small depositors as the deposit is absorbed into the reserve cash balance while zero cTokens are minted in return

### Root Cause

In [`float.move:63-65`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/math/sources/float.move#L63-L65) the `int_mul` function performs floor division:

```move
// mint amount = deposit / exchange_rate
// exchange_rate = (cash + borrows - reserves) / total_supply
// mint = deposit_amount * total_supply / (cash + borrows - reserves)
```

When the exchange rate is high (e.g., after significant interest accrual) and the deposit amount is small:

```
mint_amount = int_mul(inverse_exchange_rate, deposit_amount)
            = (inverse_rate.value * deposit_amount) / WAD
            = 0  (if product < WAD)
```

The depositor's tokens are added to the reserve's cash balance, but zero cTokens are minted. There is no minimum deposit check or zero-mint revert in the deposit flow ([`reserve.move`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move)).

### Internal Pre-conditions

1. [Interest accrual over time needs to increase the exchange rate to set] the cToken exchange rate to be high enough that `deposit_amount / exchange_rate < 1` (truncates to 0 cTokens).

### External Pre-conditions

None.

### Attack Path

1. Exchange rate increases over time via interest accrual (e.g., `exchange_rate = 2.0` after extended lending).
2. User deposits a small amount (e.g., 1 unit of underlying).
3. `mint_amount = int_mul(inverse_exchange_rate, 1) = 0` due to floor division.
4. User's deposit is absorbed into reserve cash but zero cTokens are minted.
5. The deposit is effectively donated to existing cToken holders.

### Impact

The depositors making small deposits (relative to the exchange rate) suffer a complete loss of their deposited tokens with no cTokens received. This also creates a griefing vector where an attacker can donate small amounts to inflate the exchange rate, causing subsequent small depositors to lose funds.

### PoC

_No PoC provided._

### Mitigation

Revert if zero cTokens would be minted:

```move
let mint_amount = calculate_mint(deposit_amount, exchange_rate);
assert!(mint_amount > 0, error::deposit_too_small());
```
