Confirmed findings after reviewing all `*referral*` files and `flash_loan.move`:

1. **Flash-loan volume bypasses the “deposit” threshold for referral code eligibility (High)**
- Root cause:
  - [`flash_loan.move:119`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/entry_points/lending/flash_loan.move:119) calls `track_referral(...)` using `loan.loan_amount()`.
  - [`flash_loan.move:168`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/entry_points/lending/flash_loan.move:168) increments qualification via `referral.increase_usd_qualification(...)`.
  - Referral state is explicitly intended as deposit-only: [`internal/referral.move:48-49`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/referral.move:48).
- Attack path:
  1. Borrow flash loan.
  2. Repay via `repay_flash_loan_increase_referral_qualification`.
  3. Repeat until `accumulated_deposit_only_usd >= threshold`.
  4. Generate referral code without maintaining equivalent deposited capital.
- Impact:
  - Referral code gate can be bought via fee spend on transient flash-loan notional, not real deposits.
  - Sybil code farming becomes cheap and scalable.

2. **Sybil self-referral is possible (same-controller, different addresses) (Medium)**
- Root cause:
  - Only same-address self-referral is blocked: [`internal/referral.move:225`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/referral.move:225) (`owner != user`).
  - No anti-sybil / identity / economic-link checks in referral binding: [`internal/referral.move:206-229`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/referral.move:206).
- Attack path:
  1. Address A qualifies (via finding #1) and generates code.
  2. Same attacker controls address B and binds A’s code.
  3. B flash-loans with referral code; rebates accrue to both A (referrer) and B (referee).
  4. Attacker claims both rebates.
- Impact:
  - Effective flash-loan fee discount to a single economic actor.
  - Referral rewards intended for user acquisition can be captured by self-controlled address networks.

3. **Referral codes can be gamed for economic advantage (Confirmed, derived from #1 + #2)**
- Root cause:
  - Qualification is volume-based via flash loans, not locked deposits.
  - Multi-address self-referral is allowed.
- Attack path:
  1. Cheaply qualify throwaway referrers.
  2. Route own volume through linked sybil referees.
  3. Continuously reclaim a portion of fees via rebate claims.
- Impact:
  - Protocol fee revenue dilution and incentive-program abuse.
  - Referral metrics become economically manipulable.

Check on rebate arithmetic correctness:
- I did **not** find a direct overpayment bug in rebate math itself; split logic in [`internal/referral.move:132-138`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/referral.move:132) keeps payouts bounded by collected fee.