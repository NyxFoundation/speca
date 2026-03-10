### Colluding referrer-referee pair will capture nearly all flash loan fee revenue from the protocol

### Summary

Missing combined sum validation on `referrer_discount_bps` and `referee_discount_bps` in `update_referral_params` will cause near-total flash loan fee revenue loss for the protocol as a colluding referrer-referee pair (or self-referrer) will capture up to 99.75% of flash loan fees.

### Root Cause

In [`referral.move:244-252`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/referral.move#L244-L252) each discount parameter is independently validated to be `< 10000` (100%), but there is no check on the combined sum:

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

The fee distribution in [`track_flash_loan_usage`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/internal/referral.move#L119-L152) (referral.move:119-152) splits fees sequentially:

```move
let referee_rebates_amount = initial_fee * self.referee_discount_bps / DENOMINATOR;
let referee_rebates = fee.split(referee_rebates_amount, ctx).into_balance();

let fee_remaining = initial_fee - referee_rebates_amount;

let referrer_rebates_amount = fee_remaining * self.referrer_discount_bps / DENOMINATOR;
let referrer_rebates = fee.split(referrer_rebates_amount, ctx).into_balance();
```

The protocol's `repay_flash_loan` check (`fee_coin.value() != 0` at market.move:851) only prevents absolute zero, not near-zero fees.

### Internal Pre-conditions

1. [Admin needs to call `update_referral_params` to set] both `referee_discount_bps` and `referrer_discount_bps` to be at least 9000 BPS each.
2. [Referrer needs to create a referral code, and referee needs to register with it to set] an active referral relationship.

### External Pre-conditions

None.

### Attack Path

1. Admin (or compromised governance) calls `update_referral_params` with `referee_discount_bps = 9500` and `referrer_discount_bps = 9500` -- both pass the `< 10000` check.
2. Attacker creates a referral code and uses their own code (self-referral).
3. Attacker calls `repay_flash_loan` with a flash loan fee of 10,000 tokens:
   - `referee_rebates = 10000 * 9500 / 10000 = 9500` (to attacker as referee)
   - `fee_remaining = 10000 - 9500 = 500`
   - `referrer_rebates = 500 * 9500 / 10000 = 475` (to attacker as referrer)
   - Protocol receives: `500 - 475 = 25` tokens (0.25% of the original fee)
4. Attacker captures 99.75% of the flash loan fee.

### Impact

The protocol suffers an approximate loss of up to 99.75% of flash loan fee revenue. The colluding referrer-referee pair (or self-referrer) gains the captured fee amount. With typical flash loan volumes, this represents significant protocol revenue loss. Even without self-referral, any colluding pair captures the same amount.

### PoC

_No PoC provided._

### Mitigation

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
