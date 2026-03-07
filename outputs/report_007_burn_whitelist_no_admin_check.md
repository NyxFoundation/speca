# PackageCallerCap holder will disrupt protocol operations by burning their own whitelist capability

## Summary

`burn_whitelist` does not require `AdminCap` authorization unlike all other whitelist management functions, allowing any `PackageCallerCap` holder to unilaterally destroy their capability and remove themselves from the whitelist, potentially breaking critical protocol functions like liquidation and ADL.

## Root Cause

In [`whitelist.move:27-40`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/admin/whitelist.move#L27-L40):

```move
public fun burn_whitelist(
    app: &mut ProtocolApp,
    cap: PackageCallerCap,
) {
    app.ensure_version_matches();
    let whitelist = app.whitelist_mut();
    let cap_id = object::id(&cap);
    if (whitelist.contains(&cap_id)) {
        whitelist.remove(&cap_id);
    };
    app::burn_cap(cap);
}
```

Unlike `mint_new_whitelist` (line 9), `remove_whitelist` (line 43), and `update_permission` (line 54) which all require `_: &AdminCap`, `burn_whitelist` only requires `app: &mut ProtocolApp` (a shared object) and the `PackageCallerCap` itself. Since `PackageCallerCap` has `key, store` abilities, it can be transferred to any address.

## Internal Pre-conditions

1. A `PackageCallerCap` needs to have been issued and transferred to a third-party contract or address.
2. The cap holder (or a compromised/upgraded integration contract) needs to call `burn_whitelist`.

## External Pre-conditions

None.

## Attack Path

1. Admin mints a `PackageCallerCap` with liquidation permission and transfers it to a liquidation bot contract.
2. The liquidation bot contract is upgraded or compromised.
3. The compromised contract calls `burn_whitelist(app, cap)`.
4. The `PackageCallerCap` is destroyed and removed from the whitelist.
5. All liquidation attempts that relied on this cap now fail.
6. Without functional liquidation, underwater positions accumulate bad debt.
7. The admin must mint and configure a new cap and update all integrations.

## Impact

Destruction of a `PackageCallerCap` used for liquidation, ADL, or flash loans breaks the protocol functions that depend on it. During the period between cap destruction and admin remediation:
- Liquidations cannot proceed through the affected cap, potentially causing bad debt.
- ADL operations are blocked.
- Flash loans through the affected integration are unavailable.

The severity depends on how many caps exist and whether redundant caps are available.

## Mitigation

Add `AdminCap` requirement to `burn_whitelist`, consistent with all other whitelist management functions:

```move
public fun burn_whitelist(
    _: &AdminCap,  // Add admin authorization
    app: &mut ProtocolApp,
    cap: PackageCallerCap,
) {
    // ... existing logic
}
```
