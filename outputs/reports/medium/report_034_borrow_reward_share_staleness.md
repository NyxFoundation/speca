# Borrow Reward Shares Become Stale Between User Interactions, Enabling Reward Siphoning

## Summary

Borrow-side liquidity mining reward shares are only updated when a user explicitly interacts (borrow, repay, liquidation). Between interactions, debt grows via interest accrual but the reward share remains stale, allowing frequent interactors to capture disproportionate rewards.

## Vulnerability Detail

In `borrow.move:61-66` and `repay.move:57-62`, borrow reward shares are set using `total_borrow.floor()`:

```move
// borrow.move:61-66
let miner = market.borrow_liquidity_mining_mut<MarketType>();
miner.update_obligation_reward_manager<MarketType, CoinType>(
    get_borrow_reward_type(),
    obligation_owner_cap.id(),
    total_borrow.floor(),  // share only updates on interaction
    clock
);
```

The `total_borrow` value includes accrued interest at the moment of interaction. However, interest accrues continuously via the borrow index. Between user interactions, an obligation's actual debt grows but its reward share stays at the stale value from the last interaction.

In `reward_manager.move:325-330`, cumulative rewards per share are calculated as:

```move
pool_reward.cumulative_rewards_per_share =
    pool_reward.cumulative_rewards_per_share.add(
        unlocked_rewards.div(float::from(pool_reward_manager.total_shares))
    );
```

Since `total_shares` reflects stale borrow amounts, users with outdated (lower) shares receive fewer rewards per unit of actual debt.

## Internal Pre-conditions

1. Borrow-side liquidity mining rewards must be active.
2. Obligations must have outstanding debt with accruing interest.

## External Pre-conditions

None.

## Attack Path

1. User A and User B each borrow 1,000,000 at day 0.
2. User B repays 1 unit and re-borrows every day, updating their reward share to reflect accrued interest.
3. User A does not interact for 30 days.
4. User B's share grows to ~1,008,219 while User A's remains at 1,000,000.
5. User B earns ~0.8% more rewards daily despite identical effective positions.
6. Over time, frequent interactors systematically extract more rewards.

## Impact

**Attack scenario:**
1. Borrow reward pool: 10,000 tokens/day
2. User A borrows 1,000,000 at day 0, never interacts again. After 30 days at 10% APR, actual debt ≈ 1,008,219. But reward share stays at 1,000,000.
3. User B borrows 1,000,000 at day 0, repays 1 unit and re-borrows every day. Their share updates daily to reflect accrued interest.
4. By day 30, User B's share is ~1,008,219 while User A's is 1,000,000.
5. User B earns ~0.8% more rewards daily than User A despite identical effective positions.

Over time, frequent interactors systematically extract more borrow rewards. A sophisticated attacker can automate daily no-op interactions (repay dust + re-borrow) to maximize reward capture at the expense of passive borrowers.

Note: This does NOT affect deposit rewards, because cToken amounts are static — the exchange rate captures interest growth, not the cToken balance itself.

## Code Snippet

- `borrow.move:61-66` — Borrow reward share update uses `total_borrow.floor()`
- `repay.move:57-62` — Repay reward share update uses `total_borrow.floor()`
- `liquidate.move:92-97` — Liquidation reward share update
- `reward_manager.move:325-330` — Cumulative rewards per share calculation

## Tool used

Manual Review + Automated Analysis

## Mitigation

Either:

1. **Accrue interest on the obligation before updating reward shares** — call `refresh_obligation_borrow_interest` before setting the reward share, ensuring the share reflects the true current debt.

2. **Use a normalized share** — instead of raw debt amount, divide by the current borrow index to get a principal-equivalent share that remains stable regardless of interest accrual:

```move
let normalized_share = total_borrow.div(borrow_index).floor();
miner.update_obligation_reward_manager<MarketType, CoinType>(
    get_borrow_reward_type(),
    obligation_owner_cap.id(),
    normalized_share,
    clock
);
```
