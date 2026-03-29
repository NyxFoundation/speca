# Transfer signature replay in `_verifyTransferSignature` — no nonce, deadline, or used-signature tracking allows indefinite replay of position transfers

## Lines of code

- https://github.com/aspect-build/legion-protocol-contracts/blob/314e40aa0f7ee86f2785a2a7feb4a752ec311f42/src/position/LegionPositionManager.sol#L150-L166
- https://github.com/aspect-build/legion-protocol-contracts/blob/314e40aa0f7ee86f2785a2a7feb4a752ec311f42/src/sales/LegionAbstractSale.sol#L524-L546
- https://github.com/aspect-build/legion-protocol-contracts/blob/314e40aa0f7ee86f2785a2a7feb4a752ec311f42/src/sales/LegionPreLiquidApprovedSale.sol#L656-L680
- https://github.com/aspect-build/legion-protocol-contracts/blob/314e40aa0f7ee86f2785a2a7feb4a752ec311f42/src/raise/LegionCapitalRaise.sol#L440-L465

## Vulnerability details

### Scope clarification

This finding is distinct from OOS item #4 ("Signature reuse allowing multiple investments per sale"). OOS #4 covers **invest** signatures (`_verifyInvestSignature`). This finding concerns **transfer** signatures (`_verifyTransferSignature`), which authorize position transfers between investors — a completely different operation with different security implications. The vulnerable function `_verifyTransferSignature` is defined in `LegionPositionManager`, which is inherited by all 5 in-scope sale/raise contracts:

- `LegionFixedPriceSale`
- `LegionSealedBidAuctionSale`
- `LegionPreLiquidOpenApplicationSale`
- `LegionPreLiquidApprovedSale`
- `LegionCapitalRaise`

The vulnerability manifests through the `transferInvestorPositionWithAuthorization()` function exposed in each of these in-scope contracts.

### Description

`_verifyTransferSignature()` in `LegionPositionManager.sol` (L150-166) is a **`view` function** — it verifies ECDSA signatures but performs no state mutation. There is no nonce, no deadline/expiry, and no used-signature tracking:

```solidity
function _verifyTransferSignature(
    address _from,
    address _to,
    uint256 _positionId,
    address _signer,
    bytes calldata _signature
)
    internal
    view       // ← never invalidates the signature
    virtual
{
    bytes32 _data = keccak256(
        abi.encodePacked(_from, _to, _positionId, msg.sender, address(this), block.chainid)
    ).toEthSignedMessageHash();
    if (_data.recover(_signature) != _signer) {
        revert Errors.LegionSale__InvalidSignature(_signature);
    }
}
```

The signed data is `(from, to, positionId, msg.sender, address(this), block.chainid)`. Once a valid signature is produced and used on-chain, it remains valid **indefinitely** for the same `msg.sender` (relayer). If the position ever returns to the original `from` address, the relayer can replay the signature to force-transfer the position again without current authorization from `legionSigner`.

### Inconsistency with invest signatures

The protocol already recognizes the need for replay protection. `LegionPreLiquidApprovedSale` implements `s_usedSignatures` tracking for invest/claim/withdraw signatures:

```solidity
// LegionPreLiquidApprovedSale.sol L59-60
mapping(address => mapping(bytes => bool)) private s_usedSignatures;

// L967-970
function _verifySignatureNotUsed(bytes calldata _signature) private view {
    if (s_usedSignatures[msg.sender][_signature])
        revert Errors.LegionSale__SignatureAlreadyUsed(_signature);
}
```

Transfer signatures lack equivalent protection. This is an internal inconsistency — the same protocol applies replay protection for one category of signatures but not another.

### Impact

A relayer that was authorized for a **single** position transfer gains **permanent** transfer authority over that specific `(from, to, positionId)` tuple. The attack requires:

1. A position was transferred A→B via the relayer using signature S
2. The position returns to A through any mechanism (e.g., a separate authorized B→A transfer)
3. The relayer replays signature S to force-transfer A→B again

**Concrete impact scenarios:**

- **Position theft/griefing**: A malicious or compromised relayer can repeatedly force-transfer a position away from its owner every time it returns, effectively creating a permanent "claim" on the position
- **Capital manipulation in PreLiquidApprovedSale**: When positions merge (receiver already holds a position), `cachedInvestAmount` and `cachedTokenAllocationRate` are modified — repeated forced merges could manipulate these values
- **Denial of service**: An investor who received a position back cannot safely hold it, as the old relayer retains permanent replay capability

The relayer operates at a **lower trust level** than `legionSigner` (the relayer is just a transaction submitter, not a protocol authority), yet gains indefinite transfer authority over the specific position.

## Proof of Concept

```
Step 1 — Initial authorized transfer:
  Legion signer signs: (Alice, Bob, positionId=1, relayer, saleContract, chainId)
  → produces signature S

  relayer calls: saleContract.transferInvestorPositionWithAuthorization(Alice, Bob, 1, S)
  → _verifyTransferSignature: signature valid ✅ — NO state change (view function)
  → _verifyCanTransferInvestorPosition(1): passes (not settled, not refunded, excess claimed)
  → _burnOrTransferInvestorPosition(Alice, Bob, 1): position transferred to Bob
  → Signature S is NOT invalidated anywhere

Step 2 — Position returns to Alice:
  Via separate authorized transfer (new signature for Bob→Alice), position 1 returns to Alice.

Step 3 — Replay attack:
  relayer calls: saleContract.transferInvestorPositionWithAuthorization(Alice, Bob, 1, S)
  → _verifyTransferSignature: signature S STILL valid because:
    • _from = Alice (owns position again) ✅
    • _to = Bob ✅
    • _positionId = 1 ✅
    • msg.sender = relayer (same caller) ✅
    • address(this) unchanged ✅
    • block.chainid unchanged ✅
    • Signature was NEVER invalidated ✅
  → _verifyCanTransferInvestorPosition(1): passes (position state was reset)
  → Position forcibly transferred without current authorization from legionSigner

  This can be repeated every time the position returns to Alice.
```

## Recommended mitigation

Add used-signature tracking to `_verifyTransferSignature`, consistent with the existing `s_usedSignatures` pattern:

```solidity
mapping(bytes => bool) private s_usedTransferSignatures;

function _verifyTransferSignature(
    address _from,
    address _to,
    uint256 _positionId,
    address _signer,
    bytes calldata _signature
)
    internal
    virtual  // no longer `view`
{
    if (s_usedTransferSignatures[_signature]) {
        revert Errors.LegionSale__SignatureAlreadyUsed(_signature);
    }

    bytes32 _data = keccak256(
        abi.encodePacked(_from, _to, _positionId, msg.sender, address(this), block.chainid)
    ).toEthSignedMessageHash();
    if (_data.recover(_signature) != _signer) {
        revert Errors.LegionSale__InvalidSignature(_signature);
    }

    s_usedTransferSignatures[_signature] = true;
}
```

Alternatively, add a `deadline` parameter to the signed data and check `block.timestamp <= deadline` to make signatures time-bounded.

## Assessed type

Other
