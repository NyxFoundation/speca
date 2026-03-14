**Findings**

1. **High: `PackageCallerCap` is transferable and not bound to package identity, so whitelisted privileges can be delegated to arbitrary users/contracts**
- Root cause:
  - [`contracts/protocol/sources/internal/app.move:24`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/app.move:24) defines `PackageCallerCap has key, store` (transferable object).
  - Permission checks only validate cap object ID bits, not caller package/address intent: [`app.move:159`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/app.move:159).
  - Comment indicates intent is “only certain packages”: [`app.move:24`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/app.move:24).
- Attack path:
  - Admin grants permissions to a cap via whitelist.
  - Cap holder transfers/sells/leaks the cap object.
  - New holder can invoke privileged endpoints (`flash_loan`, `liquidate`, `enter_market_with_emode`) using that cap.
- Impact:
  - Access control is effectively “whoever holds the cap object,” not “specific trusted package(s).”
  - Trusted-integration permissions can be reused by unintended actors.

2. **Medium: `burn_whitelist` lacks `AdminCap` gate, allowing non-admin whitelist mutation/destruction**
- Root cause:
  - [`contracts/protocol/sources/entry_points/admin/whitelist.move:27`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/entry_points/admin/whitelist.move:27) `burn_whitelist` has no `&AdminCap` parameter, unlike `mint_new_whitelist`, `remove_whitelist`, `update_permission`.
- Attack path:
  - Any holder of a `PackageCallerCap` can call `burn_whitelist(app, cap)` directly.
  - This removes the cap ID from whitelist and destroys the cap object.
- Impact:
  - Unauthorized state change in admin-managed whitelist registry.
  - Operational DoS/griefing against whitelisted integrations (self-burn or burn by anyone who obtains the cap).

**Direct answers to your checklist**
1. `burn_whitelist` does **not** require `AdminCap` (confirmed vulnerable).
2. `PackageCallerCap` holders can exceed intended **identity scope** (package-level trust), though not the bitmask itself (confirmed).
3. Not all admin functions are properly gated: `burn_whitelist` is missing `AdminCap` (confirmed).
4. Version-check bypass: **no confirmed bypass** in reviewed files; admin/public entrypoints consistently call `ensure_version_matches()` or use `migrate()` internal check.
5. Permission model correctness: bitmask logic is consistent for permission IDs `0..3`, but model is weak for package-binding intent due to transferable unbound caps.