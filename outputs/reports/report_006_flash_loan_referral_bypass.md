# Attacker will cheaply generate referral codes via flash loan volume inflation

## Summary

`repay_flash_loan_increase_referral_qualification` counts the full flash loan principal toward the referral qualification threshold, allowing anyone to qualify for referral code generation at ~0.1% of the intended cost by taking a single flash loan instead of maintaining actual deposits.

## Root Cause

In [`flash_loan.move:119`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/lending/flash_loan.move#L119), the function passes `loan.loan_amount()` (the full borrowed principal) to the referral tracking:

```move
track_referral(referral, ctx.sender(), loan.loan_amount(), ...);
```

The `track_referral` function at [`flash_loan.move:149-169`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/lending/flash_loan.move#L149-L169) calls `referral.increase_usd_qualification(who, collateral_value_usd.floor())`, which accumulates the flash loan amount in `accumulated_deposit_only_usd`.

The referral code generation threshold (`referrer_deposit_usd_threshold`, default $10,000) was designed for actual deposits that lock capital, but flash loans require zero capital — the borrower repays atomically in the same transaction. Combined with sybil self-referral (two addresses controlled by the same entity), the attacker can earn ongoing referral commissions cheaply.

## Internal Pre-conditions

1. The referral system needs to be active with `referrer_deposit_usd_threshold` set (default: $10,000).
2. Flash loans need to be available for any supported asset.

## External Pre-conditions

None.

## Attack Path

1. Attacker calls `borrow_flash_loan` for $10,000+ worth of any supported token (e.g., USDC).
2. In the same PTB, attacker calls `repay_flash_loan_increase_referral_qualification`. The $10,000 principal is credited to `accumulated_deposit_only_usd`. Cost: only the flash loan fee (~0.1% = ~$10).
3. Attacker calls `generate_referral_code` to obtain a referral code.
4. Attacker uses a second address (Address B) and calls `repay_flash_loan_increase_referral_qualification` with the referral code to bind Address B.
5. All future flash loan fees paid by Address B generate referral rebates: 4% to referee (Address B), ~9.6% to referrer (Address A).
6. Both addresses are controlled by the attacker, recovering ~13.6% of all flash loan fees.

## Impact

The referral qualification threshold ($10,000 deposit) is bypassed for ~$10 (the flash loan fee). This allows large-scale referral farming where attackers:
- Generate referral codes cheaply
- Self-refer via sybil addresses
- Recover ~13.6% of all flash loan fees paid through their referral network
- Reduce protocol flash loan fee revenue by the same percentage

## PoC

The field name `accumulated_deposit_only_usd` at `referral.move:49` and the comment "only allow referral code generation if deposit usd is more than `referrer_deposit_usd_threshold`" confirm the threshold was intended for actual deposits, not flash loan volume.

The cost comparison:
- **Intended**: $10,000 actual deposit (locked capital, opportunity cost)
- **Actual**: $10 flash loan fee (no capital lock, instant qualification)

## Mitigation

Either:
1. Remove the call to `increase_usd_qualification` from the flash loan repayment path, so flash loan volume does not count toward referral qualification.
2. Create a separate `repay_flash_loan` function that does not interact with the referral system (the current `repay_flash_loan` at `flash_loan.move:57` already does this — remove the `_increase_referral_qualification` variant or restrict it to actual deposit volume).
3. Track flash loan volume separately from deposit volume and require actual deposits for referral qualification.
