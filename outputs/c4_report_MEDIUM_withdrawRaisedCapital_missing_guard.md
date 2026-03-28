# Severity rating

QA Report (low)

# Title

`withdrawRaisedCapital` override in PreLiquid contracts drops `whenTokensSupplied` modifier — project can withdraw capital without supplying tokens

# Links to root cause

- https://github.com/aspect-build/legion-protocol-contracts/blob/314e40aa0f7ee86f2785a2a7feb4a752ec311f42/src/sales/LegionPreLiquidApprovedSale.sol#L322-L335
- https://github.com/aspect-build/legion-protocol-contracts/blob/314e40aa0f7ee86f2785a2a7feb4a752ec311f42/src/sales/LegionPreLiquidOpenApplicationSale.sol#L253-L265
- https://github.com/aspect-build/legion-protocol-contracts/blob/314e40aa0f7ee86f2785a2a7feb4a752ec311f42/src/sales/LegionAbstractSale.sol#L195-L204

# Vulnerability details

## Finding description and impact

`LegionAbstractSale.withdrawRaisedCapital()` (L195-204) includes `whenTokensSupplied` as a critical safety modifier that prevents the project from withdrawing raised capital before supplying tokens to investors. This modifier enforces the trustless guarantee: investors' capital is held hostage until the project fulfills its obligation.

However, both `LegionPreLiquidApprovedSale` and `LegionPreLiquidOpenApplicationSale` override `withdrawRaisedCapital()` and **drop** `whenTokensSupplied` from the modifier list.

**Base class (protected):**
```solidity
// LegionAbstractSale.sol L195-204
function withdrawRaisedCapital()
    external virtual onlyProject
    whenNotPaused
    whenRefundPeriodIsOver
    whenSaleNotCanceled
    whenSaleResultsArePublished
    whenTokensSupplied          // ← PRESENT — prevents withdrawal before token supply
{
```

**PreLiquidApprovedSale override (unprotected):**
```solidity
// LegionPreLiquidApprovedSale.sol L322-335
function withdrawRaisedCapital()
    external
    onlyProject
    whenNotPaused
    whenSaleNotCanceled
    whenSaleEnded
    whenRefundPeriodIsOver
    // whenTokensSupplied       ← MISSING
{
```

**PreLiquidOpenApplicationSale override (unprotected):**
```solidity
// LegionPreLiquidOpenApplicationSale.sol L253-265
function withdrawRaisedCapital()
    external
    override(ILegionAbstractSale, LegionAbstractSale)
    onlyProject
    whenNotPaused
    whenSaleEnded
    whenRefundPeriodIsOver
    whenSaleNotCanceled
    // whenTokensSupplied       ← MISSING
{
```

**Contracts that correctly inherit the guard:**
- `LegionFixedPriceSale` — no override, inherits `whenTokensSupplied` ✅
- `LegionSealedBidAuctionSale` — no override, inherits `whenTokensSupplied` ✅

**Impact:** In `LegionPreLiquidApprovedSale` and `LegionPreLiquidOpenApplicationSale`, the project admin can:
1. Wait for sale to end and refund period to pass
2. Call `withdrawRaisedCapital()` to withdraw all invested capital
3. Never call `supplyTokens()` — investors cannot claim tokens
4. Investors lose their invested capital with no recourse

While `onlyProject` restricts the caller to the project admin (a trusted role), the `whenTokensSupplied` modifier exists specifically to protect investors from project misbehavior. Its removal defeats the purpose of having it in the base class.

## Recommended mitigation steps

Add `whenTokensSupplied` to both override functions:

```solidity
// LegionPreLiquidApprovedSale.sol
function withdrawRaisedCapital()
    external
    onlyProject
    whenNotPaused
    whenSaleNotCanceled
    whenSaleEnded
    whenRefundPeriodIsOver
    whenTokensSupplied          // ← ADD
{

// LegionPreLiquidOpenApplicationSale.sol
function withdrawRaisedCapital()
    external
    override(ILegionAbstractSale, LegionAbstractSale)
    onlyProject
    whenNotPaused
    whenSaleEnded
    whenRefundPeriodIsOver
    whenSaleNotCanceled
    whenTokensSupplied          // ← ADD
{
```

# Proof of Concept (PoC)

Code walkthrough:

**Step 1:** A `LegionPreLiquidApprovedSale` is deployed. Investors participate and invest capital during the sale period.

**Step 2:** Sale ends. Refund period passes. Project calls `publishSaleResults()` to set accepted capital.

**Step 3:** Project calls `withdrawRaisedCapital()`:
- `onlyProject` ✅ (caller is project admin)
- `whenNotPaused` ✅
- `whenSaleNotCanceled` ✅
- `whenSaleEnded` ✅
- `whenRefundPeriodIsOver` ✅
- `whenTokensSupplied` — **NOT CHECKED** ← no guard
- Capital is transferred to project admin

**Step 4:** Project never calls `supplyTokens()`. Investors call `claimTokenAllocation()` but it reverts because `askToken` balance is zero.

**Comparison with base class:** In `LegionFixedPriceSale` (which inherits without override), the same `withdrawRaisedCapital()` call at Step 3 would **revert** with `LegionSale__TokensNotSupplied` because `whenTokensSupplied` is enforced.
