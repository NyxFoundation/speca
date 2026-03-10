### Referral Code Generation Uses Single-Shot Randomness and Reverts on Collision

Any user will be denied referral code creation due to collision-based DoS as the referral registry grows

### Summary

The lack of retry logic in `generate_referral_code` (single random generation with immediate abort on collision) will cause a denial-of-service on referral onboarding for new users as any user calling `generate_referral_code` will have their transaction revert when the single randomly generated code collides with an existing entry in the growing registry.

### Root Cause

In [`contracts/protocol/sources/internal/referral.move:168-170`](contracts/protocol/sources/internal/referral.move#L168-L170) the `generate_referral_code` function generates only one random 6-character code and aborts immediately on collision via `assert!(!self.code_owner.contains(referral_code), ...)` instead of implementing the documented retry loop:

```move
// 1. Generate one random code
generate_random_string(..., REFERRAL_CODE_LENGTH, ...)
// 2. Single collision check — aborts on failure
assert!(!self.code_owner.contains(referral_code), ...)
```

### Internal Pre-conditions

1. [Users need to register referral codes to grow] the referral code registry to have a non-trivial number of existing entries (increasing collision probability).

### External Pre-conditions

None.

### Attack Path

1. Registry accumulates referral codes over time through normal usage.
2. New user calls `generate_referral_code`.
3. A single random 6-character code is generated.
4. The code collides with an existing entry.
5. `assert!(!self.code_owner.contains(referral_code))` fails, and the transaction aborts.
6. User must retry with a new transaction, with no guarantee of success.
7. As the registry grows, collision probability increases, degrading referral onboarding availability.

### Impact

The new users suffer failed referral onboarding that degrades nondeterministically as the registry grows. The protocol loses growth from failed referral creation, and the namespace can be griefed over time to increase collision probability for all future users.

### PoC

_No PoC provided._

### Mitigation

Replace the single assertion with bounded retry logic (loop until an unused code is found, with a max-tries guard and explicit error when exhausted). Optionally increase namespace entropy (longer codes) to reduce collision risk.
