# Flash Loan Fee Bypass via Cross-eMode Group Selection

## Summary

Flash loan borrowers freely choose which eMode group to use, and the fee rate is looked up from that group. If the same asset exists in multiple eMode groups with different flash loan fee rates, borrowers always select the cheapest group, rendering higher-fee configurations in other groups ineffective.

## Vulnerability Detail

In `flash_loan.move:36-53`, the borrower specifies `emode_group`:

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

In `market.move:795-818`, the fee is taken from the specified group:

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

There is no requirement that the borrower has an obligation or any relationship with the specified eMode group. Any user can borrow a flash loan from any group that lists the asset.

## Impact

- **Revenue loss**: Admin-intended higher flash loan fees for specific eMode groups are bypassed
- **Fee configuration futility**: If USDC exists in eMode group 0 with 0.1% fee and eMode group 1 with 0.05% fee, all rational borrowers use group 1
- **Competitive disadvantage**: Higher-fee groups effectively offer the same flash loan service at a higher price that no one pays

The admin's only mitigation is to ensure all eMode groups have identical flash loan fees for the same asset, which defeats the purpose of per-group configuration.

## Code Snippet

- [`flash_loan.move:36-53`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/entry_points/lending/flash_loan.move#L36-L53): User chooses eMode group
- [`market.move:795-818`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/market.move#L795-L818): Fee from chosen group

## Tool used

Manual Review + Automated Analysis (Codex + Claude cross-validation)

## Recommendation

Either enforce the same flash loan fee across all eMode groups for a given asset, or remove the eMode group parameter from flash loans entirely (use a global per-asset flash loan fee).
