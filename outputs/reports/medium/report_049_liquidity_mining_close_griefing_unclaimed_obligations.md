# Liquidity Mining Pools Can Be Grief-Locked by Unclaimed Obligation Trackers

## Summary
`close_pool_reward` requires `num_obligation_reward_managers == 0`, but this counter is only decremented when each obligation performs a post-end `claim_rewards` call. A single obligation holder that never claims can indefinitely block pool closure and lock remaining reward balances.

## Vulnerability Detail
When an obligation participates in a reward index, `update_obligation_reward_manager` creates a reward tracker and increments `pool_reward.num_obligation_reward_managers`.

After reward end, the only code path that decrements this counter is inside `claim_rewards` (during `reward_tracker.extract()`), which requires an `obligation_id`-specific call.

`close_pool_reward` hard-reverts unless the counter is zero:
- `assert!(num_obligation_reward_managers == 0, error::liquidity_mining_not_all_rewards_claimed());`

There is no admin force-cleanup path for inactive/unreachable obligations. Therefore, an attacker can create one or more obligations that get registered in a reward index and then simply never claim after end. This indefinitely blocks `close_pool_reward` for that index.

Because user claiming requires the obligation owner capability path, protocol operators cannot clear abandoned trackers themselves.

## Internal Pre-conditions
1. At least one obligation must be registered in a reward pool's index.
2. The reward pool must have ended (past end time).

## External Pre-conditions
None.

## Attack Path
1. Attacker creates an obligation and participates in a reward pool (num_obligation_reward_managers incremented).
2. Reward pool ends.
3. Attacker never calls claim_rewards (the only path that decrements the counter).
4. Admin attempts close_pool_reward.
5. assert!(num_obligation_reward_managers == 0) fails, transaction aborts.
6. Pool closure is blocked, remaining reward balances are stuck.

## Impact
A single non-cooperative participant can DoS reward pool finalization:
- Remaining reward balances for that index cannot be closed out by admin.
- Reward accounting/state for the index cannot be finalized.
- Capital/reward inventory can remain stuck indefinitely in long-lived deployments.

## Code Snippet (file:line)
- `contracts/protocol/sources/internal/liquidity/reward_manager.move:130`
  `assert!(num_obligation_reward_managers == 0, error::liquidity_mining_not_all_rewards_claimed());`
- `contracts/protocol/sources/internal/liquidity/reward_manager.move:250-259`
  `num_obligation_reward_managers` is decremented only in post-end `claim_rewards`.
- `contracts/protocol/sources/internal/liquidity/reward_manager.move:381`
  `pool_reward.num_obligation_reward_managers = ... + 1;`
- `contracts/protocol/sources/entry_points/lending/liquidity_mining.move:39-50`
  Claims are bound to `obligation_owner_cap.id()` flow.

## Tool used
Manual Review + Automated Analysis

## Mitigation
Add an admin-safe cleanup/finalization path after a grace period, e.g.:
- force-prune zero-claim/zero-share trackers for ended pools,
- or allow `close_pool_reward` to proceed by migrating residual claimable balances to a separate claim contract/table.

This preserves user claimability while preventing permanent closure lock from abandoned obligations.
