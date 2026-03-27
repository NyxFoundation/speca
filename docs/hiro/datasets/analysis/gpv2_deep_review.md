# GPV2CompatibleAuction.sol -- Deep Line-by-Line Security Review

**File:** `src/GPV2CompatibleAuction.sol`
**Date:** 2026-03-27
**Known findings excluded:** M-15 (isValidSignature missing minBidUsdValue check), M-14 (Stale approval after _setAuction)

---

## GPv2Order.Data Struct Fields (from `GPv2Order.sol`)

```solidity
struct Data {
    IERC20 sellToken;      // Checked: L131 (must be active auction)
    IERC20 buyToken;       // Checked: L135 (must be s_assetOut)
    address receiver;      // Checked: L138 (must be address(this))
    uint256 sellAmount;    // Checked: L141 (!=0), L145 (<=balance)
    uint256 buyAmount;     // Checked: L155 (>= minBuyAmount)
    uint32 validTo;        // Checked: L158 (>= block.timestamp)
    bytes32 appData;       // ** NOT CHECKED **
    uint256 feeAmount;     // Checked: L162 (must be 0)
    bytes32 kind;          // Checked: L165 (must be KIND_SELL)
    bool partiallyFillable;// Checked: L168 (must be true)
    bytes32 sellTokenBalance; // Checked: L171 (must be BALANCE_ERC20)
    bytes32 buyTokenBalance;  // Checked: L171 (must be BALANCE_ERC20)
}
```

---

## Finding 1: `appData` field is unchecked -- No Security Impact (Informational)

**Location:** L123, entire `isValidSignature` function
**Observation:** The `appData` field (bytes32) is never validated. In CowSwap, `appData` is an arbitrary 32-byte value that gets hashed into the order struct hash. Since it is included in the hash verified at L128, a solver cannot change it without invalidating the signature. The contract does not need to enforce any particular `appData` value, and allowing any value is correct behavior.

**Verdict:** Informational / No issue. The hash check at L128 binds the appData to the signed order.

---

## Finding 2: Receiver Set to `address(this)` -- Purchased buyToken Accumulates in Contract

**Location:** L138: `order.receiver != address(this)`

**Analysis:** The contract requires the CowSwap order receiver to be `address(this)` (the auction contract itself). This means the buyToken (assetOut, e.g. LINK) is delivered to the auction contract, NOT to `s_assetOutReceiver`. The buyToken balance accumulates in the contract and is only swept to `s_assetOutReceiver` when the auction ends via `_onAuctionEnd` (BaseAuction L393-396).

**Implications:**
1. Between settlement and auction end, the buyToken sits in the contract. This is by design -- the `_onAuctionEnd` function transfers all `assetOut` balance to `s_assetOutReceiver`.
2. The error message at L40 is misleading: `InvalidReceiver(address receiver, address assetOutReceiver)` -- it names the second parameter `assetOutReceiver` but actually compares against `address(this)`, not `s_assetOutReceiver`. This is a documentation/naming inconsistency only.

**Verdict:** Low / Misleading error parameter name. No funds-at-risk.

---

## Finding 3: No Upper Bound on `sellAmount`

**Location:** L141-146

```solidity
if (order.sellAmount == 0) {
    revert Errors.InvalidZeroAmount();
}
uint256 assetInBalance = order.sellToken.balanceOf(address(this));
if (order.sellAmount > assetInBalance) {
    revert InsufficientAssetInBalance(...);
}
```

**Analysis:** There is no upper bound on `sellAmount` other than the contract's balance. A solver can craft an order selling the entire contract balance in a single trade. Combined with the missing `minBidUsdValue` check (M-15), this means a single CowSwap settlement could drain all auctioned tokens.

However, with the `partiallyFillable = true` requirement (L168), CowSwap can execute any amount up to `sellAmount`. The `executedAmount` in the Trade.Data struct controls actual fill. So the solver/settlement can actually fill less than `sellAmount`, but the order is valid for up to the full balance.

**Verdict:** Already covered by M-15 (missing minBidUsdValue check). The lack of upper bound itself is by design for partial fill orders.

---

## Finding 4: `balanceOf` Used for Sell Amount Validation -- TOCTOU with Partial Fills

**Location:** L144-146

```solidity
uint256 assetInBalance = order.sellToken.balanceOf(address(this));
if (order.sellAmount > assetInBalance) {
    revert InsufficientAssetInBalance(...);
}
```

**Analysis:** The `isValidSignature` is a `view` function called during CowSwap settlement. The balance is read at the time of signature verification. In a batch settlement, CowSwap processes multiple trades sequentially. If multiple orders reference this contract as the order owner:

1. Order A is validated -- balance = 100, sellAmount = 80. Valid.
2. Order A executes -- 80 tokens transferred out. Balance = 20.
3. Order B is validated -- balance was 100 at validation time (if validated before A executes), sellAmount = 50.

**However**, in CowSwap's GPv2Settlement.settle(), signature verification happens in the `recoverOrderFromTrade` call which happens before token transfers (which happen via `transferFrom` at the end). So all `isValidSignature` calls happen with the pre-settlement balance. If two orders for the same sellToken both pass validation but their combined sellAmount exceeds the balance, the second `transferFrom` would fail.

**Verdict:** Low / No issue in practice. CowSwap's `transferFrom` at settlement time provides the actual enforcement. The `balanceOf` check in `isValidSignature` is a courtesy check that prevents obviously invalid orders but does not provide the actual security guarantee.

---

## Finding 5: Elapsed Time Computation -- No Underflow Risk But Edge Case at Boundary

**Location:** L148-152

```solidity
uint256 elapsedTime = block.timestamp - auctionStart;
AssetParams memory assetParams = s_assetParams[address(order.sellToken)];
if (elapsedTime > assetParams.auctionDuration) {
    revert InvalidAuction(address(order.sellToken));
}
```

**Analysis:**
1. `auctionStart` is set to `block.timestamp` in `performUpkeep` (BaseAuction L353), so `block.timestamp >= auctionStart` always holds -- no underflow risk.
2. At `elapsedTime == assetParams.auctionDuration`, the order is still valid (uses `>`, not `>=`). This means at exactly the auction duration boundary, the price is at its lowest point (endingPriceMultiplier). This is correct behavior.
3. `auctionDuration` is `uint24` (max 16,777,215 seconds ~ 194 days). This is checked elsewhere and is a reasonable bound.

**Verdict:** No issue.

---

## Finding 6: `_getAssetOutAmount` and CowSwap Fee Model Mismatch

**Location:** L153-156

```solidity
(uint256 sellTokenUsdPrice,,) = _getAssetPrice(address(order.sellToken), true);
uint256 minBuyAmount = _getAssetOutAmount(assetParams, sellTokenUsdPrice, order.sellAmount, elapsedTime, true);
if (order.buyAmount < minBuyAmount) {
    revert InsufficientBuyAmount(order.buyAmount, minBuyAmount);
}
```

**Analysis:** The `_getAssetOutAmount` computation (BaseAuction L777-802) calculates the minimum buyAmount the contract will accept for a given sellAmount. This is based on oracle prices and the Dutch auction multiplier.

In CowSwap, for a partially fillable sell order, the actual settlement works as follows:
- The solver specifies `executedAmount` (the amount actually sold)
- CowSwap computes `executedBuyAmount = (executedAmount * buyAmount) / sellAmount` (proportional)
- The contract's `isValidSignature` is called with the FULL order (not the executed amounts)

**Critical insight:** The `isValidSignature` validates `order.buyAmount >= minBuyAmount` where `minBuyAmount` is computed from `order.sellAmount`. But CowSwap settles proportionally. So if `sellAmount = 100` and `buyAmount = 50`, but the solver only executes `executedAmount = 1`, the contract receives `1 * 50 / 100 = 0` (due to rounding down). For very small partial fills, integer division rounding could cause the contract to receive 0 buyToken while giving away 1 sellToken.

However, this is bounded: the minimum buyAmount enforced by `_getAssetOutAmount` ensures a reasonable ratio. The rounding loss per trade is at most 1 wei of buyToken, which is economically negligible.

**Verdict:** Informational. Rounding on very small partial fills is at most 1 wei loss.

---

## Finding 7: `feeAmount != 0` Check

**Location:** L161-164

```solidity
if (order.feeAmount > 0) {
    revert InvalidFeeAmount();
}
```

**Analysis:** In CowSwap, `feeAmount` is deducted from the sell token before computing the trade. For a sell order: `sellAmount + feeAmount` is the total amount taken from the user. By requiring `feeAmount == 0`, the contract ensures that the full `sellAmount` goes to the trade and none is taken as protocol fee.

This is correct. If feeAmount were non-zero, the vault relayer would pull `sellAmount + feeAmount` from the contract, but the contract only validates that `sellAmount <= balance`. A non-zero feeAmount could cause:
1. The vault relayer to pull more than the validated amount
2. An effective price worse than what was validated

The check correctly prevents this.

**Verdict:** No issue. Correctly implemented.

---

## Finding 8: `order.kind` Must Be `KIND_SELL`

**Location:** L165-167

```solidity
if (order.kind != GPv2Order.KIND_SELL) {
    revert InvalidOrderKind(order.kind);
}
```

**Analysis:** If a buy order were allowed, the semantics change:
- For a sell order: sell exactly `sellAmount`, receive at least `buyAmount`
- For a buy order: buy exactly `buyAmount`, sell at most `sellAmount`

With a buy order, the `executedAmount` controls how much buyToken is received, and the sellAmount becomes a maximum. The price computation in `_getAssetOutAmount` assumes sell order semantics. Allowing buy orders would break the price validation logic entirely.

**Verdict:** No issue. Correctly enforced.

---

## Finding 9: `partiallyFillable` Must Be `true` -- Critical Design Decision

**Location:** L168-170

```solidity
if (!order.partiallyFillable) {
    revert OrderNotPartiallyFillable();
}
```

**Analysis:** If `partiallyFillable` were false (fill-or-kill), the order must be fully filled or not at all. This would mean:
1. The solver must sell exactly `sellAmount` in one settlement
2. Multiple solvers cannot compete to fill portions of the order
3. If `sellAmount = balanceOf(address(this))`, the entire balance would be sold in one transaction

Requiring `partiallyFillable = true` allows:
1. Multiple partial fills over the auction duration
2. Better price discovery through competition
3. The same order can be reused across multiple settlements

**Important implication:** Since the order is partially fillable, `isValidSignature` validates the order parameters but CowSwap can execute any amount from 1 wei up to `sellAmount`. The price ratio (`buyAmount / sellAmount`) determines the per-unit price for ALL partial fills. This means the price is locked at the time the order is validated, not at execution time. If the auction price moves (due to time decay), a new order with updated parameters must be submitted.

**Verdict:** No issue. Correctly enforced. But see Finding 11 for implications.

---

## Finding 10: `sellTokenBalance` and `buyTokenBalance` Checks

**Location:** L171-173

```solidity
if (order.sellTokenBalance != GPv2Order.BALANCE_ERC20 || order.buyTokenBalance != GPv2Order.BALANCE_ERC20) {
    revert InvalidTokenBalanceMarker();
}
```

**Analysis:** CowSwap supports three balance modes:
- `BALANCE_ERC20` (keccak256("erc20")): Standard ERC20 transferFrom
- `BALANCE_EXTERNAL` (keccak256("external")): Balancer Vault external balance
- `BALANCE_INTERNAL` (keccak256("internal")): Balancer Vault internal balance

If `BALANCE_EXTERNAL` or `BALANCE_INTERNAL` were used for `sellTokenBalance`, the vault relayer would try to interact with the Balancer Vault instead of doing a direct `transferFrom`. This would fail or behave unexpectedly since the auction contract doesn't have Balancer Vault balances.

If `BALANCE_INTERNAL` were used for `buyTokenBalance`, the received tokens would be credited to an internal Balancer Vault balance instead of actually transferring ERC20 tokens. The auction contract would not receive the actual tokens.

**Verdict:** No issue. Correctly enforced.

---

## Finding 11: Price Staleness in Partially Fillable Orders

**Location:** L153-156 combined with L168

**Analysis:** The `isValidSignature` function computes `minBuyAmount` using the *current* oracle price and the *current* elapsed time in the Dutch auction. This price check happens every time `isValidSignature` is called (every settlement). So each partial fill gets re-validated against the current auction price.

However, there is a subtle issue: the `order.buyAmount` is set by the solver when creating the order. If the auction price has decayed (time has passed), a previously created order with a high `buyAmount` is still valid because `order.buyAmount >= minBuyAmount` will still pass (the minBuyAmount has decreased). But CowSwap settles proportionally: `executedBuyAmount = executedAmount * order.buyAmount / order.sellAmount`.

This means if a solver creates an order early (when the auction price is high), the per-unit price in the order is favorable to the protocol. As time passes and the auction price decays, that same order remains valid (and still gives a good price). This is correct and desirable.

Conversely, a solver could create an order late (when the price is low) and try to fill it at the low price. This is also correct -- the Dutch auction mechanism intentionally provides a decaying price.

**Verdict:** No issue. The per-call re-validation of prices means each settlement is validated against current auction state.

---

## Finding 12: ERC1271 Return Value

**Location:** L175

```solidity
return IERC1271.isValidSignature.selector;
```

**Analysis:** The ERC-1271 standard specifies that `isValidSignature` must return `0x1626ba7e` (bytes4(keccak256("isValidSignature(bytes32,bytes)"))). The `IERC1271.isValidSignature.selector` correctly computes this value, matching `GPv2EIP1271.MAGICVALUE` (verified in GPv2EIP1271.sol L8).

The CowSwap settlement contract's `recoverEip1271Signer` (GPv2Signing.sol L273-274) checks:
```solidity
require(
    EIP1271Verifier(owner).isValidSignature(orderDigest, signature) == GPv2EIP1271.MAGICVALUE,
    "GPv2: invalid eip1271 signature"
);
```

**Verdict:** No issue. Correctly implemented.

---

## Finding 13: Hash Computation at L128

**Location:** L128

```solidity
if (hash != GPv2Order.hash(order, i_gpV2Settlement.domainSeparator())) {
    revert InvalidOrderId(hash);
}
```

**Analysis:** The hash computation uses `GPv2Order.hash()` which computes the EIP-712 struct hash with the settlement contract's domain separator. The domain separator is fetched from `i_gpV2Settlement.domainSeparator()` which is an immutable value set in the settlement contract's constructor (GPv2Signing.sol L69).

**Potential concern:** The domain separator call is an external call to the settlement contract. If `i_gpV2Settlement` were compromised or pointed to a malicious contract, it could return a different domain separator, allowing crafted orders to pass validation. However, `i_gpV2Settlement` is immutable (set in constructor), so this requires the correct settlement address at deployment time.

**Second concern:** `GPv2Order.hash()` uses assembly to compute the hash in-place by temporarily overwriting memory. The implementation (GPv2Order.sol L138-143) correctly restores the overwritten memory slot, and the struct hash covers all 12 fields (416 bytes = (1 + 12) * 32). This matches the EIP-712 standard.

**Verdict:** No issue. Hash computation is correct and matches CowSwap's implementation.

---

## Finding 14: Approval Amount Set at Auction Start -- Partial Fill Reduces Balance Below Approval

**Location:** L92

```solidity
IERC20(asset).forceApprove(i_gpV2VaultRelayer, IERC20(asset).balanceOf(address(this)));
```

**Analysis:** The approval is set to the contract's balance at the time `_onAuctionStart` is called. After partial fills, the balance decreases but the approval remains at the original amount. This is not a security issue because:

1. `transferFrom` can only transfer up to `min(approval, balance)` -- so the approval being higher than the balance doesn't allow over-spending.
2. The `isValidSignature` check at L145 ensures `sellAmount <= balance`, providing an additional check.

However, if tokens are sent to the contract during an active auction (e.g., someone accidentally sends tokens), those tokens would also be approved for the vault relayer and could be sold. The `isValidSignature` check at L145 uses `balanceOf`, which would include any accidentally sent tokens.

**Verdict:** Low. Accidentally sent tokens during an active auction could be included in order validation and sold. This is an edge case with low likelihood since it requires external token transfers to the contract during an active auction. This is a variant of M-14 but focuses on excess tokens rather than stale approvals.

---

## Finding 15: `_onAuctionStart` Calls `super._onAuctionStart` Which is a No-Op

**Location:** L86-93

```solidity
function _onAuctionStart(address asset) internal override {
    super._onAuctionStart(asset);
    IERC20(asset).forceApprove(i_gpV2VaultRelayer, IERC20(asset).balanceOf(address(this)));
}
```

**Analysis:** `BaseAuction._onAuctionStart` (L375-377) is an empty virtual function. The `super` call is a no-op. This is fine -- it's defensive coding for future extensibility.

**Verdict:** No issue.

---

## Finding 16: Reentrancy Check Uses Storage Variable

**Location:** L125-127

```solidity
if (s_entered) {
    revert Errors.ReentrantCall();
}
```

**Analysis:** `isValidSignature` is a `view` function, so it cannot modify state. The `s_entered` flag is set in `BaseAuction.bid()` (L418) and cleared at L457. The reentrancy check here prevents `isValidSignature` from being called during a `bid()` call. Since `bid()` uses a callback pattern (L449: `IAuctionCallback(msg.sender).auctionCallback(...)`), a malicious callback could try to create a CowSwap settlement that calls `isValidSignature` on this contract. The check correctly prevents this.

However, `isValidSignature` is `view` and cannot modify state, so even if it were called during `bid()`, it wouldn't cause a state inconsistency. The reentrancy check here is purely defensive -- the real risk would be if `isValidSignature` returned success during an inconsistent state, allowing a CowSwap settlement to proceed with stale data.

**Verdict:** No issue. Correctly implemented defense-in-depth.

---

## Finding 17: `invalidateOrders` Access Control

**Location:** L180-186

```solidity
function invalidateOrders(
    bytes[] calldata orderUids
) external onlyRole(Roles.ORDER_MANAGER_ROLE) {
    for (uint256 i = 0; i < orderUids.length; i++) {
        i_gpV2Settlement.invalidateOrder(orderUids[i]);
    }
}
```

**Analysis:** This function calls `GPv2Settlement.invalidateOrder()` which calls `setPreSignature(orderUid, false)`. However, examining GPv2Signing.sol L77-82:

```solidity
function setPreSignature(bytes calldata orderUid, bool signed) external {
    (, address owner,) = orderUid.extractOrderUidParams();
    require(owner == msg.sender, "GPv2: cannot presign order");
    ...
}
```

Wait -- `invalidateOrder` is not `setPreSignature`. Let me re-examine. The IGPV2Settlement interface declares `invalidateOrder(bytes calldata orderUid)`. In the actual CowSwap settlement contract, `invalidateOrder` marks the order as filled (sets `filledAmount[orderUid] = type(uint256).max`), preventing further fills. This is different from `setPreSignature`.

The `invalidateOrder` function in the actual CowSwap settlement only requires that `msg.sender` matches the owner extracted from the orderUid. Since the auction contract is the order "owner" (it's the EIP-1271 signer), the auction contract can invalidate its own orders.

**Verdict:** No issue. Correctly uses the settlement's invalidation mechanism with proper access control.

---

## Finding 18: `whenNotPaused` Modifier on `isValidSignature`

**Location:** L122

```solidity
function isValidSignature(
    bytes32 hash,
    bytes memory signature
) external view whenNotPaused returns (bytes4 magicValue) {
```

**Analysis:** If the contract is paused, `isValidSignature` will revert, preventing any new CowSwap settlements. This is good for emergency stops. However, existing orders that were already submitted to CowSwap solvers will fail at settlement time. This is acceptable behavior -- pausing should stop all activity.

**Verdict:** No issue. Correctly implemented.

---

## Summary of New Findings (excluding M-14 and M-15)

| # | Severity | Title | Location |
|---|----------|-------|----------|
| 2 | Informational | Misleading error parameter name in `InvalidReceiver` | L40, L138 |
| 6 | Informational | Rounding loss on very small partial fills (max 1 wei) | L153-156 |
| 14 | Low | Accidentally sent tokens during active auction can be sold via CowSwap | L92, L144-146 |

All other checked aspects (hash computation, field validations, ERC1271 return value, reentrancy protection, access control, balance modes, order kind, fee amount, partial fillability) are correctly implemented and match the CowSwap GPv2Settlement contract's expectations.

---

## Fields Cross-Reference Summary

| GPv2Order Field | Checked in isValidSignature? | Check | Correct? |
|---|---|---|---|
| sellToken | Yes (L131) | Must have active auction | Yes |
| buyToken | Yes (L135) | Must be s_assetOut | Yes |
| receiver | Yes (L138) | Must be address(this) | Yes |
| sellAmount | Yes (L141, L145) | Non-zero, <= balance | Yes |
| buyAmount | Yes (L155) | >= minBuyAmount from auction curve | Yes |
| validTo | Yes (L158) | >= block.timestamp | Yes |
| appData | No | Not needed (bound by hash) | Yes |
| feeAmount | Yes (L162) | Must be 0 | Yes |
| kind | Yes (L165) | Must be KIND_SELL | Yes |
| partiallyFillable | Yes (L168) | Must be true | Yes |
| sellTokenBalance | Yes (L171) | Must be BALANCE_ERC20 | Yes |
| buyTokenBalance | Yes (L171) | Must be BALANCE_ERC20 | Yes |
