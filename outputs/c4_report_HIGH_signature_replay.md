# Severity rating

Medium Severity

# Title

Transfer signature replay in `_verifyTransferSignature` — no used-signature tracking allows authorized relayer to re-execute expired position transfers

# Links to root cause

- https://github.com/aspect-build/legion-protocol-contracts/blob/314e40aa0f7ee86f2785a2a7feb4a752ec311f42/src/position/LegionPositionManager.sol#L150-L166
- https://github.com/aspect-build/legion-protocol-contracts/blob/314e40aa0f7ee86f2785a2a7feb4a752ec311f42/src/sales/LegionAbstractSale.sol#L524-L546

# Vulnerability details

## Finding description and impact

`_verifyTransferSignature()` in `LegionPositionManager.sol` (L150-166) is a `view` function that verifies a transfer authorization signature but never invalidates it. There is no nonce, no used-signature mapping, and no expiry/deadline.

```solidity
// LegionPositionManager.sol L150-166
function _verifyTransferSignature(
    address _from,
    address _to,
    uint256 _positionId,
    address _signer,
    bytes calldata _signature
)
    internal
    view       // does not modify state — signature is never invalidated
    virtual
{
    bytes32 _data = keccak256(abi.encodePacked(_from, _to, _positionId, msg.sender, address(this), block.chainid))
        .toEthSignedMessageHash();
    if (_data.recover(_signature) != _signer) {
        revert Errors.LegionSale__InvalidSignature(_signature);
    }
}
```

The signature hash includes `msg.sender`, which limits the replay to the same caller (relayer) that was originally authorized. This is not a fully permissionless attack — it requires the original `msg.sender` to act maliciously or be compromised. However, once a signature is observed on-chain, it remains valid indefinitely for that caller.

**Inconsistency with invest signatures:** `LegionPreLiquidApprovedSale` already implements `s_usedSignatures` tracking for invest signatures (L59-60), demonstrating that the protocol recognizes the need for replay protection. This protection is absent for transfer signatures.

**Affected contracts:**
- `LegionAbstractSale.transferInvestorPositionWithAuthorization` (L524)
- `LegionPreLiquidApprovedSale.transferInvestorPositionWithAuthorization` (L656)
- `LegionCapitalRaise.transferInvestorPositionWithAuthorization` (L440)

**Impact scope:** If a position is transferred A→B via an authorized relayer, and later returns to A through any mechanism, the same relayer can replay the original signature to force-transfer the position A→B again without current authorization from Legion's signer. The impact is limited to:
- The specific `(from, to, positionId, msg.sender)` tuple in the original signature
- Only the original `msg.sender` can replay (not any arbitrary observer)
- The position must have returned to the original `from` address

This is a trust boundary issue: the relayer was authorized for a single transfer, but the authorization is permanent. The relayer operates at a lower trust level than `legionSigner`, yet gains indefinite transfer authority over the specific position.

## Recommended mitigation steps

Add used-signature tracking to `_verifyTransferSignature`, consistent with the existing `s_usedSignatures` pattern for invest signatures:

```solidity
mapping(bytes signature => bool used) private s_usedTransferSignatures;

function _verifyTransferSignature(
    address _from,
    address _to,
    uint256 _positionId,
    address _signer,
    bytes calldata _signature
)
    internal
    virtual
{
    if (s_usedTransferSignatures[_signature]) {
        revert Errors.LegionSale__SignatureAlreadyUsed(_signature);
    }

    bytes32 _data = keccak256(abi.encodePacked(_from, _to, _positionId, msg.sender, address(this), block.chainid))
        .toEthSignedMessageHash();
    if (_data.recover(_signature) != _signer) {
        revert Errors.LegionSale__InvalidSignature(_signature);
    }

    s_usedTransferSignatures[_signature] = true;
}
```

Alternatively, add a deadline parameter to the signed data to make signatures time-bounded.

# Proof of Concept (PoC)

The vulnerability is demonstrated via code walkthrough rather than a forge test, as the core issue is a missing state mutation (signature invalidation) that is directly observable from the code.

**Step-by-step walkthrough:**

1. **Signature issuance:** Legion's signer authorizes transfer of position `P` from Alice to Bob, signing `(Alice, Bob, P, relayer, contractAddr, chainId)` → produces signature `S`.

2. **First transfer:** `relayer` calls:
   ```solidity
   transferInvestorPositionWithAuthorization(Alice, Bob, P, S)
   ```
   - `_verifyTransferSignature` passes (signature valid) — **no state change** (view function)
   - `_verifyCanTransferInvestorPosition(P)` passes (position not settled/refunded, excess claimed)
   - `_burnOrTransferInvestorPosition(Alice, Bob, P)` executes — position now owned by Bob

3. **Position returns to Alice:** Bob transfers position back to Alice via a separate authorized transfer (new signature from legionSigner for Bob→Alice direction). Alice now owns position `P` again.

4. **Replay:** `relayer` calls again:
   ```solidity
   transferInvestorPositionWithAuthorization(Alice, Bob, P, S)
   ```
   - `_verifyTransferSignature`: signature `S` is still valid because:
     - `_from` = Alice (owns position again) ✅
     - `_to` = Bob ✅
     - `_positionId` = P ✅
     - `msg.sender` = relayer (same caller) ✅
     - `address(this)` unchanged ✅
     - `block.chainid` unchanged ✅
     - **Signature was never invalidated** — no `s_usedTransferSignatures` check ✅
   - `_verifyCanTransferInvestorPosition(P)` passes (position state was reset)
   - `_burnOrTransferInvestorPosition(Alice, Bob, P)` executes — **position forcibly transferred without current authorization**

**Root cause evidence:** Compare with invest signature protection that DOES exist:
```solidity
// LegionPreLiquidApprovedSale.sol L59-60 — invest signatures ARE tracked
mapping(address => mapping(bytes => bool)) private s_usedSignatures;

// L967-970
function _verifySignatureNotUsed(bytes calldata _signature) private view {
    if (s_usedSignatures[msg.sender][_signature]) revert Errors.LegionSale__SignatureAlreadyUsed(_signature);
}
```

Transfer signatures lack equivalent protection.
