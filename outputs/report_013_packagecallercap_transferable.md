# PackageCallerCap is Transferable Due to `store` Ability

## Summary

`PackageCallerCap` has `key, store` abilities, making it freely transferable between addresses. A whitelisted entity can delegate its protocol permissions to any arbitrary user or contract by simply transferring the cap object, bypassing the admin-controlled whitelist minting process.

## Vulnerability Detail

The `PackageCallerCap` struct in `app.move:25-27` is defined with both `key` and `store` abilities:

```move
public struct PackageCallerCap has key, store {
    id: UID,
}
```

In Sui Move, the `store` ability allows an object to be:
- Transferred to any address via `transfer::public_transfer()`
- Stored inside other objects
- Wrapped and unwrapped freely

The admin minting flow (`whitelist.move:12-25`) is properly gated by `AdminCap`:
```move
public fun mint_new_whitelist(
    _: &AdminCap,
    app: &mut ProtocolApp,
    ctx: &mut TxContext,
): PackageCallerCap {
    let cap = app::mint_cap(ctx);
    app.ensure_version_matches();
    let whitelist = app.whitelist_mut();
    whitelist.insert(object::id(&cap), 0);
    cap
}
```

However, once the cap is minted and transferred to the intended recipient, that recipient can freely transfer it to **any other address**. The permission check in `app.move:71-78` only verifies the cap's object ID exists in the whitelist — it does not verify WHO holds the cap:

```move
public fun permissions(self: &ProtocolApp, cap: &PackageCallerCap): u32 {
    let whitelist = dynamic_field::borrow<PackageWhitestKey, VecMap<ID, u32>>(&self.id, PackageWhitestKey {});
    let id = object::id(cap);
    assert!(whitelist.contains(&id), error::caller_not_whitelisted());
    *whitelist.get(&id)
}
```

## Impact

- **Permission delegation**: A whitelisted package/address can transfer its `PackageCallerCap` to any user, giving them all the same permissions without admin approval.
- **Compromised whitelisted entity**: If a whitelisted contract has a vulnerability that allows arbitrary object transfers, an attacker can extract the `PackageCallerCap` and use it to call privileged protocol functions.
- **No revocation of holder**: The admin can only revoke permissions by removing the cap's ID from the whitelist (via `burn_whitelist`), but cannot prevent transfers of the cap itself. The admin has no visibility into who currently holds the cap.

The permissions controlled by `PackageCallerCap` include critical operations like `enter_market_with_emode`, and potentially other whitelisted actions depending on the permission bitmask.

## Code Snippet

**Cap definition with `store`:**
- [`app.move:25-27`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/app.move#L25-L27): `public struct PackageCallerCap has key, store`

**Admin-gated minting:**
- [`whitelist.move:12-25`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/entry_points/admin/whitelist.move#L12-L25): `mint_new_whitelist` requires `AdminCap`

**ID-only permission check (no holder verification):**
- [`app.move:71-78`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/app.move#L71-L78): `permissions()` only checks cap ID in whitelist

## Tool used

Manual Review + Automated Analysis (Codex + Claude cross-validation)

## Recommendation

Remove the `store` ability from `PackageCallerCap` to prevent unauthorized transfers:

```move
// Before (transferable)
public struct PackageCallerCap has key, store {
    id: UID,
}

// After (non-transferable, bound to original recipient)
public struct PackageCallerCap has key {
    id: UID,
}
```

Without `store`, the cap cannot be transferred via `transfer::public_transfer()` and can only be moved via package-internal `transfer::transfer()` calls, keeping it under protocol control.
