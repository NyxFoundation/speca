After thoroughly analyzing the emode group system, I've reviewed:

1. **emode.move** - Group creation, asset support, parameter updates, borrow tracking
2. **obligation.move** - Obligation creation (permanently bound to emode_group), deposit/borrow/repay
3. **market.move** - All handlers (mint, withdraw, borrow, repay, liquidation) and solvency checks
4. **enter_market.move** - Obligation creation with emode groups
5. **All lending entry points** - borrow, deposit, withdraw, liquidate, flash_loan
6. **limiter.move** - Rate limiting mechanism
7. **asset.move** - Global asset configs
8. **debt.move** - Debt accounting with borrow index

Key observations from analysis:

- **No migration function exists**: Obligations are permanently bound to their emode group (set at creation). "Migration" requires full unwind + new obligation.
- **Emode borrow tracker staleness** (`update_asset_borrow` with `saturating_sub`): The tracker understates actual borrows because interest on non-interacting obligations isn't reflected. This is **already known as 049a**.
- **Admin emode parameter updates resetting limiters**: Already known as **025**.
- **Flash loan emode group is caller-specified** (not obligation-bound): Allows fee shopping across groups. Partially covered by **050** and requires `PackageCallerCap`.
- **Solvency checks properly use obligation's emode group**: All deposit/borrow/withdraw/liquidation operations correctly resolve collateral_factor, borrow_weight, liquidation_factor from the obligation's emode group.
- **Shared reserve with per-emode-group limiters**: By design, not exploitable without admin misconfiguration.
- **No way to deposit/borrow assets not in the obligation's emode group**: Enforced by `borrow_mut_emode` which aborts on unsupported assets.
- **Interest accrual order in handle_borrow**: Collateral interest is intentionally NOT accrued (conservative for borrowers). Debt interest is accrued. Correct.
- **saturating_sub in tracker**: Can't cause overstatement; only understates, which is the same direction as 049a.

NO_NEW_FINDINGS: The emode group migration angle is exhausted — no migration functionality exists, the permanent binding is consistently enforced across all code paths, and all potential issues with emode borrow tracking, limiter interactions, and parameter changes are already captured by known bugs (049a, 025, 050).
