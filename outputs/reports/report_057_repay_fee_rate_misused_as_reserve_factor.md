# `repay_fee_rate` Parameter Is Used as `reserve_factor` in Interest Accrual — No Repay Fee Is Ever Charged

## Summary

`AssetConfig.repay_fee_rate` is documented as "fee rate paid to the protocol in repay" but is exclusively used as the `reserve_factor` parameter in `reserve.accrue_interest()`. No actual fee is ever charged during repayment. This means the protocol has no independent `reserve_factor` configuration, and the admin parameter named `repay_fee_rate` silently controls a completely different mechanism (protocol's share of accrued interest), leading to potential misconfiguration of reserve accumulation.

## Vulnerability Detail

In `asset.move:21-22`, the `AssetConfig` struct defines:

```move
/// fee rate paid to the protocol in repay
repay_fee_rate: Decimal,
```

However, this field is **never used** in the repay flow. In `repay.move`, the full repayment path (`repay_on_behalf`) charges zero fees — the entire repaid amount goes to reducing debt and restoring `cash`:

```move
// repay.move:51-55 (simplified)
let repay_coin = coin::split(&mut coin, repay_value, ctx);
market.handle_repay<MarketType, CoinType>(obligation_id, repay_coin, now);
```

And `handle_repay` (market.move:445-494) calls `obligation.repay_debt()` then `reserve.repay_amount()` — neither deducts a fee.

The **only** usage of `repay_fee_rate` in the entire codebase is at `market.move:1025`:

```move
fun accrue_interest<MarketType>(
    coin_type: TypeName,
    reserves: &mut GenericCoinTypeStorage<Reserve<MarketType>>,
    asset: &AssetConfig,
    interest_model: &InterestModel,
    now: u64,
): &mut Reserve<MarketType> {
    let reserve = reserves.load_mut_by_type(coin_type);
    let interest_rate = interest_model.calc_interest(reserve.util_rate());
    reserve.accrue_interest(asset.repay_fee_rate(), interest_rate, now);  // <-- used as reserve_factor
    reserve
}
```

Where `reserve.accrue_interest` (reserve.move:125-149) uses the parameter as `reserve_factor`:

```move
public(package) fun accrue_interest<MarketType>(
    self: &mut Reserve<MarketType>,
    reserve_factor: Decimal,  // <-- this IS the repay_fee_rate value
    interest_rate: Decimal,
    now: u64,
) {
    // ...
    let interest_accumulated = self.debt.mul(simple_interest_factor);
    self.debt = self.debt.add(interest_accumulated);
    self.cash_reserve = self.cash_reserve.add(reserve_factor.mul(interest_accumulated));
    // ...
}
```

The `reserve_factor` determines what fraction of accrued interest goes to `cash_reserve` (protocol treasury, extractable via `take_revenue`). The remainder `(1 - reserve_factor) * interest` benefits depositors through exchange rate growth.

### Numeric Impact

The integration test constant is `repay_fee_rate(): u64 { return 1 }` (1 basis point = 0.01%). As the `reserve_factor`, this means:

- For a $100M lending market at 5% APR generating $5M annual interest:
  - Protocol treasury receives: $5M × 0.01% = **$500/year**
  - Depositors receive: $5M × 99.99% = $4,999,500/year

For comparison, typical DeFi lending protocols use `reserve_factor` of 10-25%, which would yield $500K-$1.25M in protocol revenue from the same market.

If the admin sets `repay_fee_rate = 100` (1%, a reasonable value for a repay fee), they're actually setting `reserve_factor = 1%`, generating only $50K in protocol revenue — likely far below what's needed for protocol sustainability and bad debt coverage.

## Internal Pre-conditions

1. An asset must be configured with a `repay_fee_rate` value by the admin via `create_market_asset_config`.
2. The admin must believe they are setting a repay fee rate (as documented) rather than the reserve factor.

## External Pre-conditions

None.

## Attack Path

This is not an active attack but a systematic protocol misconfiguration risk:

1. Admin deploys a market with `repay_fee_rate = 100` basis points, intending a 1% fee on repayments.
2. No repay fee is ever collected — borrowers repay the exact amount owed with zero protocol fee.
3. Instead, `reserve_factor` is set to 1%, meaning 99% of accrued interest benefits depositors and only 1% goes to protocol treasury.
4. Protocol treasury accumulates revenue at a fraction of the intended rate.
5. During a market downturn, the protocol lacks sufficient reserves to absorb bad debt from underwater positions.
6. The admin has no way to independently configure both a repay fee and a reserve factor — only one parameter exists, and it controls only the reserve factor despite its name.

## Impact

1. **Missing repay fee**: The protocol collects zero revenue from repayment transactions despite having a parameter explicitly documented for this purpose. This is protocol revenue leakage for every repayment event.

2. **Misconfigured reserve factor**: Because the admin parameter is named `repay_fee_rate`, reasonable values for a fee (1-100 bps) translate to abnormally low reserve factors (0.01%-1%), far below the 10-25% range standard in DeFi lending. The protocol under-accumulates reserves for bad debt coverage.

3. **No independent control**: The protocol cannot simultaneously configure a repay fee AND a reserve factor. These are fundamentally different mechanisms (one-time fee vs. ongoing interest share), but only one parameter exists for both, and it only controls the reserve factor.

## Code Snippet

- [`asset.move:21-22`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/asset.move#L21-L22): `repay_fee_rate` field documented as "fee rate paid to the protocol in repay"
- [`market.move:1025`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/market.move#L1025): `repay_fee_rate` passed as `reserve_factor` to `accrue_interest`
- [`reserve.move:125-149`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L125-L149): `accrue_interest` uses the value as `reserve_factor`
- [`repay.move`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/entry_points/repay.move): Full repay flow — no fee charged
- [`admin/asset.move:75`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/entry_points/admin/asset.move#L75): Admin sets `repay_fee_rate` in basis points
- [`constants.move:46`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/tests/integration/constants.move#L46): Test value `repay_fee_rate(): u64 { return 1 }` (1 bps)

## Tool used

Manual Review + Automated Analysis (SPECA Pipeline)

## Recommendation

### Option A: Rename and add a separate repay fee

Rename `repay_fee_rate` to `reserve_factor` in `AssetConfig`, and implement an actual repay fee mechanism if desired:

```move
public struct AssetConfig has copy, drop, store {
    min_borrow_amount: u64,
    max_borrow_amount: u64,
    max_deposit_amount: u64,
    reserve_factor: Decimal,        // renamed: protocol's share of accrued interest
    repay_fee_rate: Decimal,        // NEW: actual fee charged on repayment
    liquidation_fee_rate: Decimal,
}
```

### Option B: Rename only (if no repay fee is intended)

If the protocol intentionally has no repay fee, rename the field to `reserve_factor` to prevent admin confusion:

```move
/// fraction of accrued interest allocated to protocol treasury
reserve_factor: Decimal,
```

And update the admin-facing parameter name in `create_market_asset_config` accordingly.
