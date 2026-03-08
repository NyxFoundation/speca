# Admin eMode Update Resets Rate Limiter State

## Summary

When an admin updates eMode parameters via `update_asset_in_emode_group`, the rate limiter configuration is overwritten with fresh values. This resets the limiter's tracked outflow segments, effectively clearing the sliding window and allowing immediate large withdrawals/borrows that should have been rate-limited.

## Vulnerability Detail

The eMode update function in `emode.move:280-311` overwrites limiter fields:

```move
public(package) fun update(emode: &mut EMode, params: NewEMode) {
    // ... collateral, borrow params overwritten ...

    // Limiter parameters are part of NewEMode
    // When the entire limiter config is replaced, the segment history is lost
}
```

The `Limiter` struct tracks sliding window segments with timestamps and cumulative values. When the admin updates eMode parameters (even for unrelated fields like collateral factor), the limiter state can be reset because the `NewEMode` struct replaces the entire configuration.

## Internal Pre-conditions

1. eMode group must have active rate limiter with recorded outflow segments.
2. Admin must update any eMode parameter for the group.

## External Pre-conditions

None.

## Attack Path

1. Rate limiter has tracked 900/1000 capacity used in current window.
2. Admin updates `collateral_factor` for the eMode group (routine parameter change).
3. Limiter state is overwritten with fresh `NewEMode` config, clearing segment history.
4. Attacker (monitoring mempool) immediately withdraws/borrows up to the full 1000 capacity.
5. Rate limiter protection is effectively bypassed.

## Impact

- **Rate limit bypass**: An attacker monitoring mempool can front-run an admin eMode update transaction, then immediately after the update executes a large withdrawal/borrow that would have been blocked by the previous limiter state
- **Admin operational risk**: Routine parameter adjustments (e.g., updating collateral factor) inadvertently reset rate limiter protection
- **Combined with no-timelock (report_015)**: Instant eMode changes plus limiter resets create a window for large-scale extraction

## Code Snippet

- [`emode.move:280-311`](https://github.com/pebble-protocol/sui-move-contract/blob/8171fa8/contracts/protocol/sources/internal/emode.move#L280-L311): `update` overwrites limiter config

## Tool used

Manual Review + Automated Analysis (Codex + Claude cross-validation)

## Mitigation

Separate rate limiter configuration from eMode parameter updates, or preserve existing segment data when only non-limiter parameters change:

```move
public(package) fun update(emode: &mut EMode, params: NewEMode) {
    // Update collateral/borrow params...

    // Only reset limiter if limiter-specific params changed
    if (params.limiter_changed()) {
        emode.reset_limiter(params.new_limiter_config());
    }
    // Otherwise: preserve existing limiter segments
}
```
