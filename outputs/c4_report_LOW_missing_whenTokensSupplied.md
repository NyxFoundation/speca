# Severity rating

QA Report (low)

# Title

Missing `whenTokensSupplied` modifier on `LegionAbstractSale.claimTokenAllocation` — inconsistent guard compared to `withdrawRaisedCapital` and `LegionPreLiquidApprovedSale`

# Links to root cause

- https://github.com/aspect-build/legion-protocol-contracts/blob/314e40aa0f7ee86f2785a2a7feb4a752ec311f42/src/sales/LegionAbstractSale.sol#L251-L262
- https://github.com/aspect-build/legion-protocol-contracts/blob/314e40aa0f7ee86f2785a2a7feb4a752ec311f42/src/sales/LegionPreLiquidApprovedSale.sol#L397-L409
- https://github.com/aspect-build/legion-protocol-contracts/blob/314e40aa0f7ee86f2785a2a7feb4a752ec311f42/src/sales/LegionAbstractSale.sol#L195-L204

# Vulnerability details

## Finding description and impact

`LegionAbstractSale.claimTokenAllocation()` (L251) is missing the `whenTokensSupplied` modifier. Two closely related functions correctly include it:

- `LegionPreLiquidApprovedSale.claimTokenAllocation()` (L397) — **has** `whenTokensSupplied`
- `LegionAbstractSale.withdrawRaisedCapital()` (L195) — **has** `whenTokensSupplied`

```solidity
// LegionAbstractSale.sol L251 — MISSING whenTokensSupplied
function claimTokenAllocation(...) external virtual
    whenNotPaused whenSaleNotCanceled whenRefundPeriodIsOver whenSaleResultsArePublished
{  // ← no whenTokensSupplied

// LegionPreLiquidApprovedSale.sol L397 — HAS whenTokensSupplied
function claimTokenAllocation(...) external
    whenNotPaused whenSaleNotCanceled whenSaleEnded whenRefundPeriodIsOver whenTokensSupplied
{  // ✅

// LegionAbstractSale.sol L195 — HAS whenTokensSupplied
function withdrawRaisedCapital() external virtual onlyProject
    whenNotPaused whenRefundPeriodIsOver whenSaleNotCanceled whenSaleResultsArePublished whenTokensSupplied
{  // ✅
```

**Practical impact is limited (defense-in-depth):**

Under normal operation, `claimTokenAllocation` calls `SafeTransferLib.safeTransfer` (L306, L311) which reverts if the contract has insufficient token balance. This acts as a natural guard when tokens have not been supplied.

The inconsistency becomes relevant only if tokens are sent directly to the contract address (not via `supplyTokens()`), which is a non-standard path. In that scenario, claims could succeed before `supplyTokens()` fee accounting has executed. However, this requires operator error (admin misconfiguration) and is not a permissionless attack path.

**Affected child contracts:** `LegionFixedPriceSale`, `LegionSealedBidAuctionSale`, `LegionPreLiquidOpenApplicationSale`.

## Recommended mitigation steps

Add `whenTokensSupplied` to `LegionAbstractSale.claimTokenAllocation()` for consistency:

```solidity
function claimTokenAllocation(
    uint256 amount,
    LegionVestingManager.LegionInvestorVestingConfig calldata investorVestingConfig,
    bytes32[] calldata proof
)
    external
    virtual
    whenNotPaused
    whenSaleNotCanceled
    whenRefundPeriodIsOver
    whenSaleResultsArePublished
    whenTokensSupplied          // ← add
{
```

# Proof of Concept (PoC)

N/A — defense-in-depth issue. The inconsistency is directly observable by comparing modifier lists across the three functions cited above.
