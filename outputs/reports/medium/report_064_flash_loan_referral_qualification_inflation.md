### Flash Loan Referral Qualification Inflation via Principal-Based Tracking

**Severity:** Medium

**Relevant contracts:**
- `protocol::flash_loan::repay_flash_loan_increase_referral_qualification`
- `protocol::flash_loan::track_referral`
- `protocol::referral::increase_usd_qualification`

---

## Summary

The `repay_flash_loan_increase_referral_qualification` function tracks the **full loan principal** (not the fee paid) toward the user's `accumulated_deposit_only_usd` referral qualification threshold. This allows an attacker to cheaply reach the `referrer_deposit_usd_threshold` (default: $10,000) by flash-loaning a large amount and paying only the small flash loan fee (typically 0.1%), then generating a referral code to earn referral rebates on other users' flash loan fees.

## Vulnerability Detail

In `flash_loan.move` line 119, `repay_flash_loan_increase_referral_qualification` calls:

```move
track_referral(referral, ctx.sender(), loan.loan_amount(), ...);
```

Where `loan.loan_amount()` returns the full borrowed principal. Inside `track_referral` (line 149-169), this principal is converted to USD value and passed to `referral.increase_usd_qualification(who, collateral_value_usd.floor())`.

The `increase_usd_qualification` function simply accumulates the USD value:

```move
*current = *current + deposit_usd;
```

The intended purpose of `accumulated_deposit_only_usd` is to gate referral code generation behind users who have meaningful economic activity in the protocol (i.e., deposited significant amounts). However, flash loans require no collateral commitment -- the user only pays the flash loan fee (e.g., 0.1% of the principal).

**Attack scenario:**
1. Default threshold is $10,000 USD (`referrer_deposit_usd_threshold`).
2. Attacker flash-loans $10,000 worth of tokens in a single transaction.
3. The attacker pays only the flash loan fee: ~$10 (0.1% of $10,000).
4. `accumulated_deposit_only_usd` for the attacker is credited with $10,000.
5. Attacker now qualifies to generate a referral code.
6. Attacker distributes referral code and earns rebates (default: 10% of flash loan fees = `referrer_discount_bps` 1000/10000) on every referred user's flash loan.

For even cheaper attacks, the attacker could use a single flash loan of $10,000+ in a low-fee emode group.

## Impact

- The referral qualification threshold, designed to ensure only genuine depositors can create referral codes, is completely bypassed.
- An attacker can generate a referral code for the cost of a single flash loan fee (~0.1% of threshold), which is 1000x cheaper than actually depositing the threshold amount.
- This devalues the referral system and allows sybil-like referral code farming: create many addresses, qualify each cheaply with flash loans, distribute codes, and earn a percentage of referred users' flash loan fees indefinitely.
- Protocol loses revenue to inflated referral rebates paid to undeserving referrers.

## Code Snippet

**flash_loan.move lines 90-124:**
```move
public fun repay_flash_loan_increase_referral_qualification<MarketType, CoinType>(
    app: &mut ProtocolApp,
    market: &mut Market<MarketType>,
    coin: Coin<CoinType>,
    loan: FlashLoan<MarketType, CoinType>,
    maybe_referral_code: Option<String>,
    coin_decimals_registry: &CoinDecimalsRegistry,
    x_oracle: &XOracle,
    clock: &Clock,
    ctx: &mut TxContext,
) {
    // ...
    let referral = app.referral_mut();
    // BUG: loan.loan_amount() is the PRINCIPAL, not the fee
    track_referral(referral, ctx.sender(), loan.loan_amount(), ...);
    // ...
}
```

**flash_loan.move lines 149-168 (track_referral):**
```move
fun track_referral(
    referral: &mut protocol::referral::Referral,
    who: address,
    token_amount: u64,  // This is the full principal
    // ...
) {
    if (referral.is_qualified_to_create_referral_code(who)) return;
    let decimals = coin_decimals_registry.decimals(token_type);
    let usd_price = get_price(x_oracle, token_type, x_oracle::x_oracle::usd(), clock);
    let collateral_value_usd = coin_value(usd_price, math::float::from(token_amount), decimals);
    // Credits FULL principal value, not fee
    referral.increase_usd_qualification(who, collateral_value_usd.floor());
}
```

## Recommendation

Track the **fee amount** instead of the principal toward referral qualification:

```move
// In repay_flash_loan_increase_referral_qualification:
track_referral(referral, ctx.sender(), loan.fee(), ...);
// Instead of:
track_referral(referral, ctx.sender(), loan.loan_amount(), ...);
```

Alternatively, do not count flash loan activity toward referral qualification at all, since flash loans require no capital commitment. Only actual deposits (via `handle_mint`) should count toward the deposit threshold.

## Tool Used

Manual Review
