# Sybil Self-Referral Possible via Multiple Addresses

## Summary

The referral system only blocks self-referral from the same address (`owner != user`). A user can trivially create two Sui addresses, generate a referral code from address A, and use it from address B, capturing referral rebates for both referrer and referee roles.

## Vulnerability Detail

In `referral.move:206-230`, the self-referral check is address-based only:

```move
public(package) fun try_map_referral_code(
    self: &mut Referral,
    user: address,
    maybe_referral: Option<String>,
): Option<String> {
    // ...
    let code = *maybe_referral.borrow();
    assert!(self.code_owner.contains(code), error::referral_invalid_referral_code());
    let owner = self.code_owner.borrow(code);
    assert!(owner != user, error::referral_no_self_reference());  // Only same-address check
    self.referee_to_code.add(user, code);
    maybe_referral
}
```

The deposit threshold for code generation (checked in `generate_referral_code`) is:
```move
assert!(accumulated_deposit_only_usd >= referrer_deposit_usd_threshold, ...);
```

This raises the capital requirement but does not prevent a well-capitalized user from:
1. Depositing $10,000+ from address A to qualify for referral code generation
2. Generating a referral code from address A
3. Using the code from address B when depositing/borrowing
4. Both addresses earning rebates (referrer + referee discounts)

Combined with flash loan referral bypass (report_006), the deposit threshold can also be circumvented.

## Impact

- **Referral fee leakage**: Users capture both sides of referral rebates, extracting protocol revenue
- **Competitive unfairness**: Organic referrals compete against self-referral extractors
- **Combined with report_006**: Flash loans can bypass the deposit threshold, making self-referral nearly free

## Code Snippet

- [`referral.move:225`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/referral.move#L225): `assert!(owner != user, ...)` — only same-address blocked

## Tool used

Manual Review + Automated Analysis (Codex + Claude cross-validation)

## Recommendation

Consider on-chain identity verification or time-weighted deposit requirements that cannot be flash-loaned. At minimum, require the referred user to maintain a position for a minimum duration before referral rewards activate.
