After thorough analysis of the limiter system and related code, I've examined multiple potential "splitting" attack vectors:

**Angles analyzed:**

1. **Borrow-repay-borrow in same segment (PTB)**: Works (limiter shows 0 after repay, re-borrow succeeds), but net outflow is correctly bounded. Attacker needs external tokens to repay, and net drain = limit. No bypass.

2. **Cross-emode-group splitting**: The same asset can exist in multiple emode groups with separate limiters, so borrowing from each group drains the shared reserve while each group's limiter only tracks its own outflow. However, `enter_market_with_emode` (emode.move line 36) requires a whitelisted `PackageCallerCap` — regular users can only create obligations in the default emode group. Not exploitable without admin action.

3. **Cross-segment repay not reducing past outflow**: `reduce_outflow` only affects the current segment (line 114-118), so repaying in segment S+1 doesn't reduce segment S's recorded outflow. This is **documented by design** (code comment at line 98-99). It's conservative (overestimates outflow), not exploitable.

4. **Liquidation/flash loan limiter bypass**: Both intentionally skip the limiter (line 745: `// NOTE: disable rate limit`). Liquidation requires underwater positions (unprofitable self-liquidation). Flash loans are atomic (no net drain).

5. **repay_on_behalf reducing wrong group's limiter**: Repay uses `obligation.emode_group()` to find the correct limiter — always affects the obligation's own group.

6. **Amount mismatches**: Borrow limiter tracks `borrow_amount` (line 402), same value passed to `reserve.borrow_amount` (line 438). Repay limiter reduces by `coin.value()` (line 483), which is the actual repaid amount post-refund. Deposit/withdraw amounts are consistent in underlying token terms.

NO_NEW_FINDINGS: The limiter is correctly scoped per-emode-group, regular users cannot create cross-group obligations, and borrow-repay-borrow within a segment correctly bounds net outflow. All token amount tracking is consistent. The reduce_outflow single-segment behavior is conservative by design.
