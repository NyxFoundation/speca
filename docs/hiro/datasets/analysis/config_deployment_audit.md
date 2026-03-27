# Configuration, Deployment & Hardcoded Values Audit
## Chainlink Payment Abstraction V2

**Date:** 2026-03-27
**Scope:** Constructor parameters, immutables, hardcoded values, deployment configuration, bounds checking

**Known findings excluded:** H-01, M-01, M-02, M-03, M-07, M-14, M-15

---

## 1. Repository Structure Observations

- **No deployment scripts found** in the project's own `script/` directory (directory does not exist). All deployment must rely on external tooling or manual construction of constructor parameters.
- **Minimal .env.example:** Contains only `MAINNET_RPC_URL=your-rpc`. No template for constructor parameters, no documentation of required addresses per chain.
- **No deployment configuration files** (e.g., JSON config per chain, deployment manifests).

This absence of deployment infrastructure is itself a risk: there are no guardrails, checklists, or parameterized scripts to prevent misconfigurations during production deployment.

---

## 2. Constructor Parameter Audit

### 2.1 BaseAuction Constructor

**File:** `src/BaseAuction.sol` lines 179-200

```solidity
constructor(ConstructorParams memory params)
  PriceManager(params.adminRoleTransferDelay, params.admin, params.verifierProxy, params.linkToken, params.feedInfos)
{
    if (params.assetOut == address(0) || params.assetOutReceiver == address(0)) {
      revert Errors.InvalidZeroAddress();
    }
    _setMinBidUsdValue(params.minBidUsdValue);
    _setAssetOut(params.assetOut);
    _setAssetOutReceiver(params.assetOutReceiver);
    _setFeeAggregator(params.feeAggregator);
    if (params.minPriceMultiplier == 0) {
      revert Errors.InvalidZeroValue();
    }
    i_minPriceMultiplier = params.minPriceMultiplier;
}
```

**ConstructorParams struct:**
```solidity
struct ConstructorParams {
    address admin;
    uint48 adminRoleTransferDelay;
    uint64 minPriceMultiplier;
    address verifierProxy;
    uint88 minBidUsdValue;
    address linkToken;
    address assetOut;
    address assetOutReceiver;
    address feeAggregator;
    PriceManager.ApplyFeedInfoUpdateParams[] feedInfos;
}
```

#### Findings:

**[C-01] No upper bound on `i_minPriceMultiplier` (immutable) -- Low**

- **Type:** `uint64` (max ~18.4e18)
- **Intended semantics:** Multiplier with 18 decimal precision. A value of `1e18` = 1x (no discount). The documented example uses `0.98e18` for 2% max discount.
- **Issue:** Only checked for `!= 0`. A deployer could set this to `2e18` or any absurd value. Since this is immutable, the contract would need redeployment.
- **Upper bound constraint:** Should be `<= 1e18` (no premium required at minimum). A value above `1e18` means the ending price multiplier must also be above `1e18`, which forces every auction to always sell at a premium -- potentially making auctions unsettleable.
- **Impact:** Low -- admin-controlled parameter. But since it is immutable and cannot be corrected post-deployment, a misconfiguration would brick the auction contract.

**[C-02] No upper bound on `minBidUsdValue` (mutable, `uint88`) -- Informational**

- **Max value:** `uint88` max = ~309,485 in 18-decimal USD terms (~3e26 / 1e18 = ~3e8 = ~$309M).
- **Check:** Only `!= 0`. An ASSET_ADMIN could set this extremely high, effectively pausing bids.
- **Mitigated by:** Mutable state, can be corrected by ASSET_ADMIN.

**[C-03] `adminRoleTransferDelay` accepts zero -- Informational**

- **Type:** `uint48`
- **Check:** None (passed directly to OZ `AccessControlDefaultAdminRules`).
- **Issue:** Setting `adminRoleTransferDelay = 0` means admin transfers are instant, eliminating the timelock protection. OZ allows this, but it defeats the security purpose.
- **Impact:** Informational -- deployment configuration concern.

**[C-04] `_setAssetOut` in constructor calls `_whenNoLiveAuctions` -- No issue**

- The internal `_setAssetOut` calls `_whenNoLiveAuctions()`, which iterates `s_allowlistedAssets`. At construction time this set is empty, so the check passes trivially. No gas concern.

**[C-05] `_setFeeAggregator` allows `address(this)` -- By design**

- When `feeAggregator == address(this)`, the ERC165 check is skipped. This is intentional: the auction contract acts as its own fee aggregator (no external pull). Verified in `performUpkeep` line 318: `bool hasFeeAggregator = address(s_feeAggregator) != address(this)`.

### 2.2 GPV2CompatibleAuction Constructor

**File:** `src/GPV2CompatibleAuction.sol` lines 69-83

```solidity
constructor(
    BaseAuction.ConstructorParams memory params,
    address gpV2VaultRelayer,
    address gpV2Settlement
) BaseAuction(params) {
    if (gpV2VaultRelayer == address(0) || gpV2Settlement == address(0)) {
      revert Errors.InvalidZeroAddress();
    }
    i_gpV2VaultRelayer = gpV2VaultRelayer;
    i_gpV2Settlement = IGPV2Settlement(gpV2Settlement);
}
```

#### Findings:

**[C-06] CowSwap addresses are immutable with no on-chain validation -- Medium/Low**

- `i_gpV2VaultRelayer` and `i_gpV2Settlement` are stored as immutables after only a zero-address check.
- **No interface check** (unlike `_setFeeAggregator` which checks ERC165, or `_setAuction` in AuctionBidder).
- **No chain-specific validation**: CowSwap (CoW Protocol) is only deployed on Ethereum mainnet, Gnosis Chain, Arbitrum, and Base. Deploying this contract on an unsupported chain with incorrect addresses would brick the CowSwap integration permanently (immutable).
- **Risk:** If the deployer provides wrong addresses (e.g., mainnet addresses on a testnet, or a non-CowSwap address), the contract cannot be fixed without redeployment.
- **Recommendation:** Consider adding an ERC165 or `domainSeparator()` call check in the constructor to validate the settlement contract is functional.

**[C-07] GPV2CompatibleAuction approves full balance to VaultRelayer on auction start -- By design (known)**

- In `_onAuctionStart`, `forceApprove` is called with `balanceOf(address(this))`. This is the full balance at auction start time.
- If tokens are sent directly to the contract between auction start and settlement, they would not be included in the approval. This is actually protective -- only the intended auction amount is approved.

### 2.3 AuctionBidder Constructor

**File:** `src/AuctionBidder.sol` lines 42-53

```solidity
constructor(
    uint48 adminRoleTransferDelay,
    address admin,
    address auction,
    address receiver
) PausableWithAccessControl(adminRoleTransferDelay, admin) {
    _setAuction(auction);
    if (receiver != address(0)) {
      _setReceiver(receiver);
    }
}
```

#### Findings:

**[C-08] `receiver` can be zero address (no funds forwarding) -- By design**

- If `receiver == address(0)`, `_setReceiver` is skipped. The `bid()` function checks `if (receiver != address(0))` before transferring, so leftover `assetOut` simply stays in the contract.
- This is intentional per the "optional receiver" documentation.

**[C-09] `_setAuction` validates ERC165 `IBaseAuction` interface -- Good**

- The auction bidder performs an ERC165 check, which is stronger validation than GPV2CompatibleAuction does for its CowSwap addresses.

**[C-10] No validation that `admin` is not zero in `PausableWithAccessControl` -- Informational**

- `PausableWithAccessControl` passes `admin` to `AccessControlDefaultAdminRules(adminRoleTransferDelay, admin)`.
- OZ's `AccessControlDefaultAdminRules` **does** check for zero admin address (reverts with `AccessControlInvalidDefaultAdmin`), so this is handled by the dependency.

### 2.4 PriceManager Constructor

**File:** `src/PriceManager.sol` lines 107-125

```solidity
constructor(
    uint48 adminRoleTransferDelay,
    address admin,
    address verifierProxy,
    address linkToken,
    ApplyFeedInfoUpdateParams[] memory feedsInfo
) LinkReceiver(linkToken) EmergencyWithdrawer(adminRoleTransferDelay, admin) {
    if (verifierProxy == address(0)) {
      revert Errors.InvalidZeroAddress();
    }
    i_streamsVerifierProxy = IVerifierProxy(verifierProxy);
    if (feedsInfo.length > 0) {
      _applyFeedInfoUpdates(feedsInfo, new address[](0));
    }
}
```

#### Findings:

**[C-11] `verifierProxy` is immutable with no interface validation -- Low**

- Only zero-address check. No ERC165 or functional call to validate the verifier proxy is operational.
- Since this is immutable, a wrong address would permanently prevent price transmission via Data Streams.
- **Chain-specific risk:** The VerifierProxy address differs per chain. A mainnet address used on a testnet (or vice versa) would silently fail during `verifyBulk` calls.

**[C-12] `linkToken` is immutable (set in `LinkReceiver`) with no interface validation -- Low**

- `LinkReceiver` constructor only checks `!= address(0)`, then casts to `IERC20`.
- No check that the address is actually the LINK token on the deployment chain.
- LINK token addresses differ across chains (e.g., `0x514910771AF9Ca656af840dff83E8264EcF986CA` on Ethereum mainnet, different addresses on L2s/sidechains).

**[C-13] `stalenessThreshold` in FeedInfo has no upper bound -- Low**

- `_applyFeedInfoUpdates` checks `stalenessThreshold != 0` but has no maximum.
- **Type:** `uint32` (max ~4.29 billion seconds = ~136 years).
- A very large staleness threshold effectively disables staleness checks, allowing arbitrarily old prices.
- **Mitigated by:** ASSET_ADMIN role is trusted, and the value is mutable.

**[C-14] `dataStreamsFeedDecimals` has no upper bound -- Informational**

- **Type:** `uint8` (max 255).
- If set higher than 18, the `transmit` function would perform `usdPrice / 10 ** (feedDecimals - PRICE_DECIMALS)`, potentially truncating the price to zero.
- The zero-price check (`if (usdPrice == 0) revert Errors.ZeroFeedData()`) would catch this, but it means a misconfigured feed would be non-functional rather than silently wrong.

### 2.5 FeeAggregator Constructor

**File:** `src/FeeAggregator.sol` lines 136-149

```solidity
constructor(ConstructorParams memory params)
    EmergencyWithdrawer(params.adminRoleTransferDelay, params.admin)
    LinkReceiver(params.linkToken)
    NativeTokenReceiver(params.wrappedNativeToken)
{
    if (params.ccipRouterClient == address(0)) {
      revert Errors.InvalidZeroAddress();
    }
    i_ccipRouter = IRouterClient(params.ccipRouterClient);
}
```

#### Findings:

**[C-15] `ccipRouterClient` is immutable with no interface validation -- Low**

- Same pattern as other immutables: zero-check only. No ERC165 or functional validation.
- CCIP Router addresses differ per chain.

**[C-16] `wrappedNativeToken` accepts zero address -- By design**

- `NativeTokenReceiver` constructor: `if (wrappedNativeToken != address(0)) { _setWrappedNativeToken(wrappedNativeToken); }`
- Intentional: "We allow setting to the zero address for chains that may not have a wrapped native token."
- **Risk:** On chains that DO have a wrapped native token, if deployer forgets to set it, `receive()` fallback won't auto-wrap. This is low risk since `setWrappedNativeToken` can fix it post-deployment.

### 2.6 WorkflowRouter Constructor

**File:** `src/WorkflowRouter.sol` lines 77-80

```solidity
constructor(
    uint48 adminRoleTransferDelay,
    address admin
) PausableWithAccessControl(adminRoleTransferDelay, admin) {}
```

- Minimal constructor with no additional parameters. All configuration is done post-deployment via `applyAllowlistedWorkflowsUpdates`. No issues.

---

## 3. Immutable Values Summary

| Contract | Immutable | Type | Zero Check | Bounds Check | Interface Check | Chain-Specific |
|---|---|---|---|---|---|---|
| BaseAuction | `i_minPriceMultiplier` | `uint64` | Yes | **No upper bound** | N/A | No |
| PriceManager | `i_streamsVerifierProxy` | `IVerifierProxy` | Yes | N/A | **No** | **Yes** |
| LinkReceiver | `i_linkToken` | `IERC20` | Yes | N/A | **No** | **Yes** |
| GPV2CompatibleAuction | `i_gpV2VaultRelayer` | `address` | Yes | N/A | **No** | **Yes** |
| GPV2CompatibleAuction | `i_gpV2Settlement` | `IGPV2Settlement` | Yes | N/A | **No** | **Yes** |
| FeeAggregator | `i_ccipRouter` | `IRouterClient` | Yes | N/A | **No** | **Yes** |

**Pattern:** All immutables have zero-address checks but none have interface/functionality validation, and all chain-specific addresses lack any on-chain verification that the address is correct for the deployment chain.

---

## 4. AssetParams Configuration Validation

**File:** `src/BaseAuction.sol`, `_applyAssetParamsUpdates` lines 598-664

```solidity
struct AssetParams {
    uint96 minAuctionSizeUsd;      // Min swap size in USD feed decimals
    uint64 startingPriceMultiplier; // Starting price multiplier (18 decimals)
    uint64 endingPriceMultiplier;   // Ending price multiplier (18 decimals)
    uint24 auctionDuration;         // Duration in seconds
    uint8 decimals;                 // Asset decimals
}
```

#### Findings:

**[C-17] `startingPriceMultiplier` has no upper bound -- Low**

- **Type:** `uint64` (max ~18.4e18).
- With 18 decimal precision, `1e18` = 1x multiplier. The max `uint64` value = ~18.4x multiplier.
- Only validated that `startingPriceMultiplier >= endingPriceMultiplier`.
- An extremely high starting multiplier would make the initial auction price absurdly expensive, but the Dutch auction mechanism would eventually decrease it. No funds at risk.

**[C-18] `startingPriceMultiplier` can equal zero if it's the assetOut -- Informational**

- For asset == assetOut, the auction-specific checks (duration, multipliers) are skipped:
  ```solidity
  if (asset != s_assetOut) { /* validate multipliers, duration */ }
  ```
- The assetOut params only require `minAuctionSizeUsd != 0` and correct `decimals`. The multiplier fields are unused for assetOut, so zero values are acceptable.

**[C-19] `auctionDuration` max is `uint24` = 16,777,215 seconds (~194 days) -- Informational**

- Type-bounded to ~194 days max. This is reasonable for an auction duration. No explicit max check needed beyond the type.

**[C-20] `minAuctionSizeUsd` type is `uint96` but no documented precision convention -- Informational**

- The struct comment says "expressed in USD feed decimals" but prices are scaled to 18 decimals internally.
- In `checkUpkeep` and `performUpkeep`, comparison is: `(assetBalance * assetPrice) / (10 ** assetParams.decimals) < assetParams.minAuctionSizeUsd`
- Since `assetPrice` is in 18-decimal USD, the resulting `assetBalanceUsdValue` is also in 18-decimal USD. So `minAuctionSizeUsd` should be in 18-decimal USD as well. The struct comment is misleading but the code is consistent.

---

## 5. Deployment Configuration Risks

**[C-21] No deployment scripts or configuration files -- Medium (Operational)**

- The repository contains no `script/` directory, no deployment manifests, and no per-chain configuration.
- The `.env.example` only has `MAINNET_RPC_URL`.
- **Risk:** Every deployment relies on manual parameter construction. For a multi-chain deployment with numerous chain-specific addresses (LINK, VerifierProxy, CowSwap VaultRelayer, CowSwap Settlement, CCIP Router, WrappedNativeToken), the probability of misconfiguration is high.
- **Recommendation:** Create deployment scripts with per-chain address registries and constructor parameter validation.

**[C-22] `foundry.toml` specifies `evm_version = "paris"` -- Informational**

- Paris EVM version is pre-Cancun (no `MCOPY`, no transient storage). This is conservative and safe for multi-chain deployment since not all chains support post-Paris opcodes.
- **No issue** -- this is a sound deployment choice.

---

## 6. Hardcoded Values

**[C-23] `PRICE_DECIMALS = 18` -- Informational (correct)**

- All price math consistently uses 18 decimals. This is standard and correct.

**[C-24] `STREAMS_REPORT_V3 = 3` -- Informational (correct)**

- Used to validate Data Streams feed ID version. Correct for current Chainlink Data Streams.

**[C-25] `MIN_GAS_FOR_RECEIVE = 2300` in NativeTokenReceiver -- Informational**

- The `receive()` function checks `gasleft() > 2300` to distinguish between `transfer()`/`send()` calls (which forward exactly 2300 gas) and regular calls.
- **Note:** Post-EIP-2929, the actual gas forwarded by `transfer()` can vary. However, the logic here is: if more than 2300 gas is available, attempt auto-wrapping. This is a best-effort mechanism with try/catch, so failures are silent and non-critical.

**[C-26] `EMPTY_ENCODED_BYTES32_ADDRESS_HASH` in FeeAggregator -- Correct**

- `keccak256(abi.encode(address(0)))` -- used to reject zero-address receivers in bridging. Correctly handles the case where receivers are passed as encoded bytes.

**[C-27] No hardcoded external addresses in source code -- Good**

- All chain-specific addresses (LINK, VerifierProxy, CowSwap, CCIP Router, WETH/WMATIC) are passed via constructor parameters. There are no hardcoded addresses in the Solidity source.

---

## 7. Missing Initialization Checks

**[C-28] No roles granted in constructors -- By design but risky**

- All constructors only set the `DEFAULT_ADMIN_ROLE` (via OZ). No other roles (PAUSER, ASSET_ADMIN, SWAPPER, etc.) are granted during construction.
- **Risk:** The contract is fully deployed but non-functional until the admin manually grants all required roles. If the admin loses access before granting roles, the contract is bricked (except for admin transfer via timelock).
- **Mitigated by:** `adminRoleTransferDelay` timelock and the fact that this is standard OZ access control behavior.

**[C-29] No initial asset configuration in BaseAuction constructor -- By design**

- `feedInfos` can be passed to configure initial price feeds, but `AssetParams` (auction parameters) cannot be set in the constructor.
- The contract requires a two-step setup: (1) deploy, (2) call `applyAssetParamsUpdates`.
- **Risk:** Between deployment and asset configuration, the contract exists in a partially configured state. The `whenAssetOutConfigured` modifier protects `checkUpkeep`/`performUpkeep` from executing without assetOut params.

---

## 8. Cross-Contract Configuration Coherence

**[C-30] FeeAggregator and BaseAuction must be configured with matching asset allowlists -- Operational**

- BaseAuction's `performUpkeep` calls `s_feeAggregator.transferForSwap(address(this), eligibleAssets)`.
- This requires the assets to be allowlisted in BOTH the FeeAggregator AND the BaseAuction.
- **Risk:** If an asset is allowlisted in BaseAuction but not in FeeAggregator, `transferForSwap` will revert, blocking auctions for that asset. This is a deployment/configuration coherence issue, not a code bug.

**[C-31] BaseAuction's `s_assetOut` must have AssetParams configured -- Protected**

- The `whenAssetOutConfigured` modifier checks `s_assetParams[s_assetOut].decimals != 0`.
- If assetOut is changed without setting new AssetParams, `checkUpkeep`/`performUpkeep`/`bid` are blocked.
- `_setAssetOut` deletes old assetOut params: `delete s_assetParams[currentAssetOut]`.
- **Risk:** Changing assetOut requires an additional `applyAssetParamsUpdates` call. If forgotten, the contract is non-functional (but safely so).

---

## 9. Consolidated Findings Table

| ID | Severity | Description | Contract | Immutable? |
|---|---|---|---|---|
| C-01 | Low | `i_minPriceMultiplier` has no upper bound; value > 1e18 could make auctions unsettleable | BaseAuction | Yes |
| C-06 | Low | CowSwap immutable addresses have no interface validation; wrong chain = permanent brick | GPV2CompatibleAuction | Yes |
| C-11 | Low | `verifierProxy` immutable has no interface validation | PriceManager | Yes |
| C-12 | Low | `linkToken` immutable has no interface validation; chain-specific | LinkReceiver | Yes |
| C-13 | Low | `stalenessThreshold` has no upper bound; large value disables staleness protection | PriceManager | No |
| C-15 | Low | `ccipRouterClient` immutable has no interface validation | FeeAggregator | Yes |
| C-21 | Medium (Ops) | No deployment scripts or per-chain configuration files | Repository | N/A |
| C-03 | Info | `adminRoleTransferDelay` accepts zero, eliminating timelock | All contracts | Yes |
| C-17 | Info | `startingPriceMultiplier` has no upper bound (uint64 max ~18.4e18) | BaseAuction | No |

---

## 10. Recommendations

1. **Create deployment scripts** with per-chain address registries for LINK, VerifierProxy, CowSwap Settlement/VaultRelayer, CCIP Router, and WETH addresses.
2. **Add constructor validation** for immutable addresses: at minimum, call a view function on the target contract to confirm it is responsive and returns expected values (e.g., `IGPV2Settlement(gpV2Settlement).domainSeparator()`).
3. **Add an upper bound check** on `i_minPriceMultiplier` (e.g., `<= 1e18`) to prevent deployment with values that make auctions impossible.
4. **Add an upper bound check** on `stalenessThreshold` (e.g., `<= 1 days` or `<= 7 days`) to prevent accidental disabling of staleness protection.
5. **Document the required post-deployment steps** (role grants, asset configuration, feed setup) in a deployment checklist.
6. **Consider a minimum `adminRoleTransferDelay`** to prevent deployment with zero timelock.
