# Same-Second Zero-Interest Borrowing via PTB

## Summary

A user can borrow and repay within the same Sui Programmable Transaction Block (PTB) to achieve zero-interest borrowing. The timestamp-based interest accrual check skips computation when `last_updated == now`, allowing the repay to occur without any interest being charged on the borrow.

## Vulnerability Detail

Interest accrual in `reserve.move:132-135` uses a timestamp equality check:

```move
public(package) fun accrue_interest<MarketType>(..., now: u64) {
    let last_updated = self.borrow_index.last_updated();
    if (last_updated == now) {
        return   // SKIP accrual if already updated this second
    };
    // ... interest calculation ...
    self.borrow_index.set_value(new_borrow_index_value, now);
}
```

Both `borrow.move:49` and `repay.move:46` compute timestamp as:
```move
let now = clock::timestamp_ms(clock) / 1000;
```

**Attack flow within a single PTB at timestamp T:**

1. **Borrow phase**: `handle_borrow()` calls `accrue_interest()`. Since `last_updated = T-1` (from a previous tx), the condition `last_updated == now` is **false**, so interest IS accrued and `last_updated` is set to `T`.

2. **Repay phase (same PTB)**: `handle_repay()` calls `accrue_interest()` again. Now `last_updated = T` and `now = T`, so the condition `last_updated == now` is **true** — the function returns early **without accruing any interest**.

3. The user's debt is repaid at exactly the same borrow index value as when they borrowed, meaning **zero interest is charged**.

This is distinct from flash loans — no hot-potato pattern is used. The user performs a standard `borrow` followed by a standard `repay` in the same PTB, bypassing both:
- The interest accrual mechanism (via timestamp skip)
- The flash loan fee (since no flash loan function is called)

## Impact

- **Free flash-loan equivalent**: Users get zero-cost borrowing for within-block operations, bypassing the protocol's flash loan fee entirely. The protocol explicitly charges flash loan fees (configurable per market) as a revenue source, but this mechanism provides the same functionality for free.
- **Interest leakage**: Even for very short-duration borrows (same second), the protocol intended to charge at least 1 second of interest. This undermines the borrowing cost model.
- **MEV/arbitrage subsidy**: Arbitrageurs and liquidators can use free same-second borrows to fund operations without any cost, extracting value that should have accrued to the protocol and lenders.

## Code Snippet

**Timestamp equality skip:**
- [`reserve.move:132-135`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/reserve.move#L132-L135): `if (last_updated == now) { return }`

**Borrow timestamp:**
- [`borrow.move:49`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/entry_points/lending/borrow.move#L49): `let now = clock::timestamp_ms(clock) / 1000`

**Repay timestamp:**
- [`repay.move:46`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/entry_points/lending/repay.move#L46): `let now = clock::timestamp_ms(clock) / 1000`

**Borrow triggers accrual and updates last_updated:**
- [`market.move:407`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/market.move#L407): `refresh_obligation_borrow_interest_with_new_borrow`
- [`market.move:901`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/market.move#L901): calls `accrue_interest()`

**Repay triggers accrual (but skips due to same timestamp):**
- [`market.move:459`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/market/market.move#L459): calls `accrue_interest()`

## Tool used

Manual Review + Automated Analysis (Codex + Claude cross-validation)

## Recommendation

Prevent borrow-then-repay within the same second:

```move
// Option 1: Track per-obligation last borrow timestamp and reject same-second repay
assert!(obligation.last_borrow_timestamp() < now, error::same_second_repay_not_allowed());

// Option 2: Charge minimum 1 second of interest on repay
let elapsed = if (now <= last_updated) { 1 } else { now - last_updated };
```
