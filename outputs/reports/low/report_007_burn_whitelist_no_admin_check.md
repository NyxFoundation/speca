### Compromised PackageCallerCap holder will disrupt liquidation, ADL, and flash loan operations for the protocol by burning their own whitelist capability

### Summary

Missing `AdminCap` authorization on `burn_whitelist` will cause a disruption of critical protocol functions (liquidation, ADL, flash loans) for the protocol as a compromised or upgraded integration contract will call `burn_whitelist` to destroy its `PackageCallerCap` and remove itself from the whitelist without admin approval

### Root Cause

In [`whitelist.move:27-40`](https://github.com/pebble-protocol/sui-move-contract/blob/8a250918a763b63449a767482a4c4a5079b30893/contracts/protocol/sources/entry_points/admin/whitelist.move#L27-L40) the `burn_whitelist` function does not require `AdminCap` authorization unlike all other whitelist management functions:

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

Unlike `mint_new_whitelist` (line 12), `remove_whitelist` (line 42), and `update_permission` (line 53) which all require `_: &AdminCap`, `burn_whitelist` only requires `app: &mut ProtocolApp` (a shared object) and the `PackageCallerCap` itself. Since `PackageCallerCap` has `key, store` abilities, it can be transferred to any address.

### Internal Pre-conditions

1. [Admin needs to mint and transfer a `PackageCallerCap` to set] the cap to be held by a third-party contract or address.
2. [The cap holder or a compromised/upgraded integration contract needs to call `burn_whitelist` to set] the cap to be destroyed.

### External Pre-conditions

None.

### Attack Path

1. Admin mints a `PackageCallerCap` with liquidation permission and transfers it to a liquidation bot contract.
2. The liquidation bot contract is upgraded or compromised.
3. The compromised contract calls `burn_whitelist(app, cap)`.
4. The `PackageCallerCap` is destroyed and removed from the whitelist.
5. All liquidation attempts that relied on this cap now fail.
6. Without functional liquidation, underwater positions accumulate bad debt.
7. The admin must mint and configure a new cap and update all integrations.

### Impact

The protocol suffers a disruption of liquidation, ADL, and flash loan operations that depend on the destroyed cap. During the period between cap destruction and admin remediation, liquidations cannot proceed through the affected cap, potentially causing bad debt accumulation. The severity depends on how many caps exist and whether redundant caps are available.

### PoC

_No PoC provided._

### Mitigation

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
