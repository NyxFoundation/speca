# Referral Discount Parameters Sum Unbounded — Protocol Can Lose Nearly All Flash Loan Fee Revenue

## Summary

`update_referral_params` validates `referrer_discount_bps` and `referee_discount_bps` individually (each must be `< DENOMINATOR`), but does not validate their combined sum. An admin misconfiguration setting both near 100% allows referral participants to capture nearly all flash loan fee revenue, leaving the protocol with negligible income.

## Root Cause

In [`referral.move:244-252`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/referral.move#L244-L252):

```move
public(package) fun update_referral_params(
    self: &mut Referral,
    referrer_discount_bps: u64,
    referee_discount_bps: u64,
    referrer_deposit_usd_threshold: u64,
) {
    assert!(referrer_discount_bps < DENOMINATOR, error::invalid_params_error());
    assert!(referee_discount_bps < DENOMINATOR, error::invalid_params_error());
    // Missing: assert!(referrer_discount_bps + referee_discount_bps <= MAX_TOTAL_DISCOUNT)
```

Each parameter is independently validated to be `< 10000` (100%), but there is no check on `referrer_discount_bps + referee_discount_bps`. Both can be set to 9999 BPS simultaneously.

The fee distribution in `track_flash_loan_usage` ([`referral.move:119-152`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/referral.move#L119-L152)):

```move
let referee_rebates_amount = initial_fee * self.referee_discount_bps / DENOMINATOR;
let referee_rebates = fee.split(referee_rebates_amount, ctx).into_balance();

let fee_remaining = initial_fee - referee_rebates_amount;

let referrer_rebates_amount = fee_remaining * self.referrer_discount_bps / DENOMINATOR;
let referrer_rebates = fee.split(referrer_rebates_amount, ctx).into_balance();
```

The referee gets `fee * referee_discount_bps / 10000` first, then the referrer gets `remaining * referrer_discount_bps / 10000`. The protocol receives what's left.

## Internal Pre-conditions

1. Admin must set both discount parameters to high values (e.g., both at 9000+ BPS).
2. A referral code must exist and be used in flash loan transactions.

## External Pre-conditions

None. This is a governance parameter validation gap.

## Attack Path

1. Admin (or compromised governance) sets `referee_discount_bps = 9500` and `referrer_discount_bps = 9500` via `update_referral_params`.
2. Attacker creates a referral code and uses their own code (self-referral, per report_019 this is possible).
3. Attacker takes a flash loan with fee of 10,000 tokens:
   - `referee_rebates = 10000 * 9500 / 10000 = 9500` (to attacker as referee)
   - `fee_remaining = 10000 - 9500 = 500`
   - `referrer_rebates = 500 * 9500 / 10000 = 475` (to attacker as referrer)
   - Protocol receives: `500 - 475 = 25` tokens (0.25% of the original fee)
4. Attacker captures 99.75% of the flash loan fee.

Even without self-referral, a referee-referrer colluding pair captures 99.75% of fees. The protocol's `repay_flash_loan` check (`fee_coin.value() != 0` at market.move:851) only prevents absolute zero, not near-zero fees.

## Impact

Protocol revenue from flash loan fees is reduced to near-zero when both referral discount parameters are set to high values. With typical flash loan volumes, this represents significant protocol revenue loss.

The severity depends on governance controls: if the admin key is a multisig with timelock, the risk is lower. If it's a single key, accidental or malicious misconfiguration could immediately drain flash loan revenue.

## PoC

Arithmetic verification:

1. `DENOMINATOR = 10000` (referral.move:15)
2. Set `referee_discount_bps = 9500`, `referrer_discount_bps = 9500` — both pass `< 10000` check
3. On fee of F tokens:
   - Referee gets: `F * 9500 / 10000 = 0.95F`
   - Remaining: `0.05F`
   - Referrer gets: `0.05F * 9500 / 10000 = 0.0475F`
   - Protocol gets: `0.05F - 0.0475F = 0.0025F` (0.25%)
4. Total referral capture: `0.95F + 0.0475F = 0.9975F` (99.75%)

## Mitigation

Add a combined discount limit check:

```move
public(package) fun update_referral_params(
    self: &mut Referral,
    referrer_discount_bps: u64,
    referee_discount_bps: u64,
    referrer_deposit_usd_threshold: u64,
) {
    assert!(referrer_discount_bps < DENOMINATOR, error::invalid_params_error());
    assert!(referee_discount_bps < DENOMINATOR, error::invalid_params_error());
    assert!(referrer_discount_bps + referee_discount_bps <= 5000, error::invalid_params_error()); // Max 50% total discount
    // ...
}
```

The combined cap (e.g., 50%) ensures the protocol always retains a minimum share of flash loan fees.
