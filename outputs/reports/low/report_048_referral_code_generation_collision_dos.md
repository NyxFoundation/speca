# Referral Code Generation Uses Single-Shot Randomness and Reverts on Collision

## Summary
`generate_referral_code` is documented as retrying until a unique code is found, but the implementation only generates one 6-character code and aborts immediately if that code already exists. This creates an avoidable denial-of-service path for referral code creation whenever collisions occur.

## Vulnerability Detail
In `protocol::referral::generate_referral_code`, the code path is:
1. Generate one random code (`generate_random_string(..., REFERRAL_CODE_LENGTH, ...)`).
2. Check uniqueness once with `assert!(!self.code_owner.contains(referral_code), ...)`.
3. Abort on collision.

There is no retry loop despite the inline comment saying it should keep generating until uniqueness is achieved. As the registry grows, collision probability increases, causing legitimate users to fail referral-code creation due to random collision rather than qualification or authorization.

## Internal Pre-conditions
1. Referral code registry must have existing codes registered (increasing collision probability).

## External Pre-conditions
None.

## Attack Path
1. Registry accumulates referral codes over time.
2. New user calls generate_referral_code.
3. Single random 6-character code is generated.
4. Code collides with existing entry.
5. assert!(!self.code_owner.contains(referral_code)) fails, transaction aborts.
6. User must retry (new transaction), with no guarantee of success.
7. As registry grows, collision probability increases, degrading referral onboarding.

## Impact
Referral onboarding can fail nondeterministically for qualified users. This degrades protocol growth and can be abused as griefing pressure by filling the namespace over time (increasing collision probability), forcing repeated failed attempts for new users.

## Code Snippet (file:line)
- `contracts/protocol/sources/internal/referral.move:168`
- `contracts/protocol/sources/internal/referral.move:169`
- `contracts/protocol/sources/internal/referral.move:170`

## Tool used
Manual Review + Automated Analysis

## Mitigation
Replace the single assertion with bounded retry logic (loop until an unused code is found, with a max-tries guard and explicit error when exhausted). Optionally increase namespace entropy (longer codes) to reduce collision risk.
