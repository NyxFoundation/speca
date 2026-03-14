### Flash loan borrower will bypass higher fee configurations via cross-eMode group selection to reduce protocol revenue

### Summary

Unrestricted eMode group selection in `borrow_flash_loan` will cause a loss of flash loan fee revenue for the protocol as any borrower will select the eMode group with the lowest flash loan fee rate for a given asset

### Root Cause

In [`flash_loan.move:36-53`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/entry_points/lending/flash_loan.move#L36-L53) the borrower specifies the eMode group with no restriction:

```move
public fun borrow_flash_loan<MarketType, CoinType>(
    // ...
    emode_group: u8,  // User-provided parameter
    amount: u64,
    ctx: &mut TxContext,
): (Coin<CoinType>, FlashLoan<MarketType, CoinType>) {
    borrow_flash_loan_inner<MarketType, CoinType>(market, amount, emode_group, ctx)
}
```

In [`market.move:795-818`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/market.move#L795-L818) the fee is taken from the specified group without verifying the borrower's relationship to it:

```move
public(package) fun borrow_flash_loan<MarketType, CoinType>(
    self: &mut Market<MarketType>,
    emode_group: u8,
    amount: u64,
    ctx: &mut TxContext,
) {
    let emode = self.emode_group_registry.borrow_emode_group(emode_group).borrow_emode(...);
    let flash_loan_fee_rate = emode.flash_loan().fee_rate();  // Fee from chosen group
    let fee = flash_loan_fee_rate.int_mul(amount);
    // ...
}
```

There is no requirement that the borrower has an obligation or any relationship with the specified eMode group.

### Internal Pre-conditions

1. [Admin needs to onboard the same asset to multiple eMode groups to set] the asset to have different flash loan fee rates across groups.

### External Pre-conditions

None.

### Attack Path

1. Admin configures asset X in eMode group 0 with 0.1% flash loan fee and eMode group 1 with 0.05% fee.
2. Borrower calls `borrow_flash_loan` specifying eMode group 1.
3. Fee is computed from group 1's lower rate.
4. Protocol collects less revenue than group 0's intended fee.

### Impact

The protocol suffers a loss of flash loan fee revenue. Admin-intended higher flash loan fees for specific eMode groups are bypassed because all rational borrowers select the cheapest group. If the same asset exists in multiple groups with different fee rates, the higher-fee configurations are rendered ineffective. The admin's only workaround is to ensure all eMode groups have identical flash loan fees for the same asset, which defeats the purpose of per-group configuration.

### PoC

_No PoC provided._

### Mitigation

Either enforce the same flash loan fee across all eMode groups for a given asset, or remove the eMode group parameter from flash loans entirely (use a global per-asset flash loan fee).
