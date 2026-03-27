# PriceManager.sol Deep Security Review

**Contract:** `src/PriceManager.sol` (427 lines)
**Solidity:** 0.8.26
**Scope:** Oracle price management for Chainlink Payment Abstraction V2
**Excluded known findings:** M-01, M-02, M-03, M-07

---

## Finding PM-01: No Oracle Price Divergence Check Between Data Streams and Chainlink Feed

**Severity:** Medium
**Location:** L384-401 (`_getAssetPrice`)

### Description

When the Data Streams price is stale and the contract falls back to the Chainlink data feed, the selection logic at L390 simply picks whichever source has the newer timestamp:

```solidity
// L385-401
if (updatedAt < minTimestamp && feedInfo.usdDataFeed != AggregatorV3Interface(address(0))) {
    (, int256 answer,, uint256 dataFeedUpdatedAt,) = feedInfo.usdDataFeed.latestRoundData();
    if (updatedAt < dataFeedUpdatedAt) {
        updatedAt = dataFeedUpdatedAt;
        price = answer.toUint256();
        // ... scale decimals ...
    }
}
```

There is no divergence check between the two oracle sources. If the Chainlink data feed returns a price that is wildly different from the Data Streams price (e.g., 10x higher or lower due to a feed misconfiguration, oracle manipulation, or a flash crash captured by one source but not the other), the contract silently accepts whichever has the newer timestamp.

### Impact

In `BaseAuction.sol`, prices are used to compute auction values and asset-out amounts (L342, L429, L798). A manipulated or erroneous price from either source -- accepted without cross-validation -- directly impacts:
- Auction start eligibility (`availableAssetUsdValue` at BaseAuction L344)
- Bid valuation (BaseAuction L430)
- Asset-out computation (BaseAuction L799-802)

An attacker who can influence one oracle source (e.g., manipulating a low-liquidity Chainlink feed) could extract value from auctions.

### Recommendation

Add a divergence threshold check when both sources have non-zero, non-stale prices. If the prices diverge by more than a configurable percentage (e.g., 5-10%), revert or use the more conservative price.

---

## Finding PM-02: Negative `int192 price` from Data Streams Report Silently Wraps via SafeCast

**Severity:** Medium
**Location:** L160

### Description

The `transmit()` function processes the `report.price` field (declared as `int192` in the `ReportV3` struct at L64) through this cast chain:

```solidity
// L160
uint256 usdPrice = int256(report.price).toUint256();
```

OpenZeppelin's `SafeCast.toUint256(int256)` reverts if the value is negative. This means a negative price from the Data Streams DON consensus would cause the entire `transmit()` call to revert for ALL reports in the batch, not just the offending one.

While the revert prevents storing a negative price (which is correct), the DoS vector is the concern: a single report with a negative price in a batch of multiple reports causes ALL price updates to fail. The `PRICE_ADMIN_ROLE` holder would need to identify and exclude the problematic report, during which time all other assets' prices become increasingly stale.

### Impact

Temporary DoS on price updates for all assets in a batch. Combined with the staleness-based fallback, this could force the system onto the Chainlink feed fallback for an extended period.

### Recommendation

Consider wrapping individual report processing in a try/catch or checking `report.price > 0` before the cast, allowing valid reports in the batch to proceed even if one report has an anomalous negative price.

---

## Finding PM-03: Chainlink Data Feed `answer` Negative Value Causes Revert in `_getAssetPrice`

**Severity:** Low
**Location:** L386, L392

### Description

```solidity
// L386
(, int256 answer,, uint256 dataFeedUpdatedAt,) = feedInfo.usdDataFeed.latestRoundData();
// L392
price = answer.toUint256();
```

If the Chainlink data feed returns a negative `answer` (which is possible for certain feeds or during extreme market conditions), `SafeCast.toUint256(int256)` reverts. Unlike `transmit()`, this revert occurs in the view function `_getAssetPrice` which is called during critical auction operations (BaseAuction L315, L342, L429).

When called with `withValidation = true` (as in `performUpkeep` at BaseAuction L315 and `bid` at BaseAuction L429), this revert propagates up and blocks:
- Starting new auctions
- Processing bids on existing auctions
- GPV2 order validation

The stale Data Streams price that triggered the fallback would already be present in `s_dataStreamsPrice`, so the system has no working price source.

### Impact

If the Chainlink feed for the `assetOut` returns a negative value, all auction operations halt because every bid and performUpkeep path calls `_getAssetPrice(s_assetOut, true)`.

### Recommendation

Before calling `answer.toUint256()`, check `answer > 0`. If negative, skip the data feed result and leave the (stale) Data Streams price, allowing the staleness check at L405 to correctly flag `isValid = false`.

---

## Finding PM-04: `stalenessThreshold` Close to `block.timestamp` Causes Underflow (Solidity 0.8.26)

**Severity:** Low
**Location:** L378

### Description

```solidity
// L378
uint256 minTimestamp = block.timestamp - feedInfo.stalenessThreshold;
```

`feedInfo.stalenessThreshold` is `uint32` (max value: 4,294,967,295 seconds, approximately 136 years). On a freshly deployed chain or in test environments, if `block.timestamp` is smaller than `stalenessThreshold`, this subtraction underflows and reverts due to Solidity 0.8.26 checked arithmetic.

While `type(uint32).max` exceeds any realistic `block.timestamp` value on mainnet today (~1.7 billion seconds), the configuration validation at L244 only checks `stalenessThreshold != 0`. There is no upper bound check.

Setting `stalenessThreshold` to `type(uint32).max` (4294967295) would cause `_getAssetPrice` to revert on any chain where `block.timestamp < 4294967295` (i.e., before year 2106). On mainnet today, `block.timestamp` is approximately 1.7 billion, so any `stalenessThreshold` greater than `block.timestamp` causes a revert.

### Impact

An `ASSET_ADMIN_ROLE` holder setting an excessively large `stalenessThreshold` (e.g., > ~54 years from now) would brick all price queries for that asset, halting auctions.

### Recommendation

Add an upper bound validation on `stalenessThreshold` during `_applyFeedInfoUpdates`. A reasonable maximum might be 30 days (2,592,000 seconds).

---

## Finding PM-05: `stalenessThreshold = 0` Blocked But Adjacent Value `1` Makes Everything Stale

**Severity:** Informational
**Location:** L244, L378, L162

### Description

The configuration correctly rejects `stalenessThreshold == 0` at L244. However, setting `stalenessThreshold = 1` means `minTimestamp = block.timestamp - 1`. Any price older than 1 second is considered stale. Since `transmit()` also checks staleness at L162 using the same threshold, a report whose `observationsTimestamp` is even 2 seconds old would be rejected.

In practice, Data Streams reports always have some latency (DON consensus time + transmission time), so `stalenessThreshold = 1` effectively makes it impossible to ever store a valid price.

### Impact

Misconfiguration risk only. The `ASSET_ADMIN_ROLE` is trusted, but there is no minimum threshold guard.

### Recommendation

Consider enforcing a minimum `stalenessThreshold` (e.g., 60 seconds) to prevent accidental misconfiguration.

---

## Finding PM-06: Immutable VerifierProxy Cannot Be Rotated if Compromised

**Severity:** Low
**Location:** L95, L118

### Description

```solidity
// L95
IVerifierProxy internal immutable i_streamsVerifierProxy;
// L118
i_streamsVerifierProxy = IVerifierProxy(verifierProxy);
```

The `VerifierProxy` is stored as `immutable`, meaning it cannot be changed after deployment. If the VerifierProxy is compromised, upgraded to return malicious data, or needs to be rotated for any reason, the entire PriceManager (and by extension, all inheriting auction contracts) must be redeployed.

While immutability is a deliberate design choice (gas savings, reduced attack surface from setter functions), it creates a rigid dependency on the VerifierProxy's integrity for the lifetime of the contract.

### Impact

If the VerifierProxy is compromised or returns garbage data from `verifyBulk()` (L153), the `transmit()` function would decode and store arbitrary prices. The only defense is the `PRICE_ADMIN_ROLE` access control on `transmit()` -- the contract trusts the VerifierProxy output entirely after verification.

### Recommendation

This is a design trade-off. Document the redeployment requirement clearly. Consider whether a governance-controlled setter with a timelock would be acceptable for the proxy address.

---

## Finding PM-07: `verifyBulk` Return Length Mismatch Not Validated

**Severity:** Medium
**Location:** L153-156

### Description

```solidity
// L153
bytes[] memory verifiedReports = i_streamsVerifierProxy.verifyBulk(unverifiedReports, abi.encode(i_linkToken));
// L155
for (uint256 i; i < verifiedReports.length; ++i) {
    ReportV3 memory report = abi.decode(verifiedReports[i], (ReportV3));
```

The first loop (L140-150) validates that each `unverifiedReports[i]` has an allowlisted `dataStreamsFeedId`. The second loop (L155-182) processes `verifiedReports` returned by the VerifierProxy.

There is no check that `verifiedReports.length == unverifiedReports.length`. If the VerifierProxy returns fewer reports (filtering some out), the pre-validation in the first loop may have validated reports that are not actually in the verified output. More critically, if the VerifierProxy returns MORE reports than submitted (due to a bug or compromise), additional reports would be processed and stored without the allowlist pre-check.

The allowlist check at L147 uses the `dataStreamsFeedId` extracted from the *unverified* report data. After verification, the second loop at L157 looks up `s_dataStreamsFeedIdToAsset[report.dataStreamsFeedId]` for the *verified* report. If the VerifierProxy returns a report for a different feed than what was submitted, the lookup at L157 would return `address(0)`, and the price would be stored for the zero address (which is not in `s_allowlistedAssets` but the mapping write still succeeds).

### Impact

In the pathological case of a compromised VerifierProxy that returns extra or different reports:
1. Prices could be stored for `address(0)` in `s_dataStreamsPrice`
2. Prices could be stored for assets whose unverified data was not pre-checked
3. The `asset` variable at L157 would be `address(0)`, and the `feedInfo` lookup would return default values (0 decimals, 0 staleness), causing the staleness check at L162 to underflow/revert

In practice, this requires a compromised VerifierProxy, but the defense-in-depth principle suggests validating the invariant.

### Recommendation

Add `require(verifiedReports.length == unverifiedReports.length)` after the `verifyBulk` call. Additionally, check that `asset != address(0)` after the L157 lookup in the second loop.

---

## Finding PM-08: Duplicate Feed ID in `transmit()` Batch Allows Price Overwrite Without Freshness Ordering

**Severity:** Low
**Location:** L155-182

### Description

The `transmit()` function processes reports sequentially. If two reports in the same batch reference the same `dataStreamsFeedId`, the second report overwrites the first at L178-179:

```solidity
// L178-179
s_dataStreamsPrice[asset] =
    DataStreamsPriceInfo({usdPrice: usdPrice.toUint224(), timestamp: report.observationsTimestamp});
```

There is no check that the second report has a newer `observationsTimestamp` than the first. A `PRICE_ADMIN_ROLE` holder could submit a batch where a newer report appears first, followed by an older report for the same asset, resulting in a stale price being stored.

While the `PRICE_ADMIN_ROLE` is trusted, this also means the ordering of reports within a `transmit()` batch matters, which is fragile and could lead to accidental staleness if the off-chain system does not sort reports correctly.

### Impact

Stale price stored for an asset if batch ordering is incorrect. This could affect auction valuations.

### Recommendation

In the second loop, before overwriting `s_dataStreamsPrice[asset]`, check that `report.observationsTimestamp > s_dataStreamsPrice[asset].timestamp`.

---

## Finding PM-09: `decimals()` Call on Chainlink Feed is Unbounded and Called on Every Price Read

**Severity:** Informational (Gas / DoS)
**Location:** L394

### Description

```solidity
// L394
uint8 decimals = feedInfo.usdDataFeed.decimals();
```

Every time `_getAssetPrice` falls back to the Chainlink data feed, it makes an external call to `decimals()` on the feed contract. This value is constant for any given Chainlink feed and never changes. The call is made in a view function, so gas cost matters less, but if the `usdDataFeed` is a malicious contract (set by `ASSET_ADMIN_ROLE`), it could:
1. Consume excessive gas in `decimals()`
2. Return different values on different calls
3. Revert selectively

### Impact

Low. The `ASSET_ADMIN_ROLE` is trusted, and `decimals()` is a standard interface. However, caching the decimals at configuration time (already done for Data Streams at L74 as `dataStreamsFeedDecimals`) would be more robust.

### Recommendation

Cache the Chainlink feed decimals in `FeedInfo` at configuration time in `_applyFeedInfoUpdates`, similar to how `dataStreamsFeedDecimals` is already cached. This also saves gas on every fallback price read.

---

## Finding PM-10: Feed Removal Does Not Check for Active `withValidation=true` Consumers

**Severity:** Low
**Location:** L217-231

### Description

When a feed is removed via `_applyFeedInfoUpdates` (L217-231), the code:
1. Calls `_onFeedInfoUpdate(asset, true)` -- overridden in BaseAuction to block removal during live auctions
2. Removes from `s_allowlistedAssets`
3. Deletes `s_dataStreamsFeedIdToAsset`, `s_feedInfo`, and `s_dataStreamsPrice`

The BaseAuction override at L688-697 checks for live auctions on the removed asset or if it is the `assetOut`. However, after removal, any call to `_getAssetPrice(asset, ...)` will:
- Return `priceInfo = {0, 0}` (deleted mapping)
- Return `feedInfo` with zero staleness threshold, which at L378 would underflow: `block.timestamp - 0 = block.timestamp`, so `minTimestamp = block.timestamp`
- Since `updatedAt = 0 < block.timestamp = minTimestamp`, enter the fallback branch
- `feedInfo.usdDataFeed` would be `address(0)`, so skip the fallback
- Return `price = 0, updatedAt = 0, isValid = false`

The `isValid = false` return is correct, but if any code path calls `_getAssetPrice(removedAsset, true)` (with validation), it would revert with `ZeroFeedData`. This is the expected behavior since the asset was removed, but the `getQuote` function at BaseAuction L764 calls `_getAssetPrice(assetIn, false)` -- so for removed assets, it returns a zero price silently, leading to division by zero at L802 if `assetOutUsdPrice` is zero.

### Impact

Low, since auction operations for removed assets should not occur (live auction check). But the zero-price return is a latent footgun for any future consumer.

### Recommendation

After feed removal, ensure no code path can silently use a zero price. Consider adding an `isAllowlisted` check in `_getAssetPrice`.

---

## Finding PM-11: `usdPrice` Stored as `uint224` Truncation Risk from Scaled Price

**Severity:** Informational
**Location:** L179

### Description

```solidity
// L179
DataStreamsPriceInfo({usdPrice: usdPrice.toUint224(), timestamp: report.observationsTimestamp});
```

After decimal scaling at L168-172, `usdPrice` is a `uint256`. The `SafeCast.toUint224()` call reverts if the value exceeds `type(uint224).max` (~2.69e67). After scaling to 18 decimals, a price would need to exceed ~2.69e49 in the token's native denomination to overflow `uint224`. This is practically unreachable for any real asset.

Similarly, at L392 in `_getAssetPrice`, the Chainlink feed's `answer.toUint256()` is stored directly as `price` (uint256) without a `toUint224()` cast. This price is returned to callers as `uint256`, so no truncation occurs in the fallback path, but the two paths return differently-sized values (Data Streams is capped at `uint224`, Chainlink feed is not).

### Impact

Negligible. The `uint224` cap is astronomically high. The inconsistency between paths is cosmetic.

---

## Finding PM-12: `_applyFeedInfoUpdates` Processes Removes Before Adds -- Order Matters for Same Asset

**Severity:** Informational
**Location:** L217-302

### Description

The function processes `removes` first (L217-231), then `adds` (L233-302). If the same asset appears in both `removes` and `adds` in a single call, it will be first removed (clearing all state including price data), then re-added with new configuration. This is likely intentional (allows atomic feed rotation), but the intermediate state deletion means any cached Data Streams price for the asset is permanently lost.

### Impact

Informational. This is expected behavior but should be documented.

---

## Summary Table

| ID | Title | Severity | Lines |
|----|-------|----------|-------|
| PM-01 | No oracle price divergence check | Medium | L384-401 |
| PM-02 | Negative int192 DoS on batch transmit | Medium | L160 |
| PM-03 | Negative Chainlink answer reverts price queries | Low | L386, L392 |
| PM-04 | Large stalenessThreshold underflows minTimestamp | Low | L378, L244 |
| PM-05 | stalenessThreshold=1 makes all prices stale | Informational | L244, L378 |
| PM-06 | Immutable VerifierProxy cannot be rotated | Low | L95, L118 |
| PM-07 | verifyBulk return length not validated | Medium | L153-156 |
| PM-08 | Duplicate feed ID overwrites without freshness check | Low | L155-182 |
| PM-09 | Chainlink decimals() not cached | Informational | L394 |
| PM-10 | Feed removal leaves zero-price footgun | Low | L217-231 |
| PM-11 | uint224 truncation risk (theoretical) | Informational | L179 |
| PM-12 | Remove-before-add ordering deletes cached prices | Informational | L217-302 |
