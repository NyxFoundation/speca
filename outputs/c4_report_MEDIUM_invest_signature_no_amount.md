# Severity rating

Medium Severity

# Title

`_verifyInvestSignature` does not include investment amount, nonce, or deadline in signed hash — allows authorized investors to invest arbitrary amounts with a single signature

# Links to root cause

- https://github.com/aspect-build/legion-protocol-contracts/blob/314e40aa0f7ee86f2785a2a7feb4a752ec311f42/src/sales/LegionAbstractSale.sol#L884-L892
- https://github.com/aspect-build/legion-protocol-contracts/blob/314e40aa0f7ee86f2785a2a7feb4a752ec311f42/src/sales/LegionPreLiquidApprovedSale.sol#L1030-L1050

# Vulnerability details

## Finding description and impact

`_verifyInvestSignature()` in `LegionAbstractSale.sol` (L884-892) constructs the signed hash from only three fields: `msg.sender`, `address(this)`, and `block.chainid`. The investment `amount`, a `nonce`, and an expiry `deadline` are all absent from the hash.

```solidity
// LegionAbstractSale.sol L884-892
function _verifyInvestSignature(bytes calldata _signature) internal view virtual {
    bytes32 _data = keccak256(abi.encodePacked(
        msg.sender,        // investor address
        address(this),     // sale contract
        block.chainid      // chain ID
    )).toEthSignedMessageMessage();
    if (_data.recover(_signature) != s_addressConfig.legionSigner) {
        revert Errors.LegionSale__InvalidSignature(_signature);
    }
}
```

This affects all three sale contracts that use this function:
- `LegionFixedPriceSale.invest()`
- `LegionSealedBidAuctionSale.invest()`
- `LegionPreLiquidOpenApplicationSale.invest()`

None of these contracts implement `s_usedSignatures` tracking or any alternative replay prevention for invest signatures.

**Inconsistency with `LegionPreLiquidApprovedSale`:** This contract uses a separate, more secure signature scheme (L1030-1050) that includes `investAmount`, `tokenAllocationRate`, `actionType`, and tracks used signatures via `s_usedSignatures`. This demonstrates the protocol recognizes the need for amount-binding and replay prevention, but failed to apply it to the three other sale types.

**Impact:**

1. **Amount bypass**: Legion's signer authorizes "user X may invest in sale Y" but cannot control HOW MUCH. An investor with a valid signature can invest any amount between `minimumInvestAmount` and the sale's capacity, regardless of what Legion intended to authorize.

2. **Signature replay**: The same signature can be used for multiple `invest()` calls. Each call accumulates `investedCapital += amount`. An investor can repeatedly invest to accumulate a larger position than intended, potentially crowding out other authorized investors.

3. **No expiry**: Once issued, a signature is valid for the entire sale duration with no way to revoke it.

## Recommended mitigation steps

Include `amount`, `nonce`, and `deadline` in the signed hash, and track used signatures:

```solidity
mapping(address => mapping(bytes => bool)) private s_usedInvestSignatures;

function _verifyInvestSignature(
    bytes calldata _signature,
    uint256 _amount,
    uint256 _deadline
) internal virtual {
    if (block.timestamp > _deadline) revert Errors.LegionSale__SignatureExpired();
    if (s_usedInvestSignatures[msg.sender][_signature]) {
        revert Errors.LegionSale__SignatureAlreadyUsed(_signature);
    }

    bytes32 _data = keccak256(abi.encodePacked(
        msg.sender, address(this), block.chainid, _amount, _deadline
    )).toEthSignedMessageHash();

    if (_data.recover(_signature) != s_addressConfig.legionSigner) {
        revert Errors.LegionSale__InvalidSignature(_signature);
    }

    s_usedInvestSignatures[msg.sender][_signature] = true;
}
```

# Proof of Concept (PoC)

Code walkthrough demonstrating the issue:

**Step 1 — Signature issuance:** Legion's signer authorizes investor Alice for a FixedPriceSale, signing `(Alice, saleContract, chainId)` → signature `S`.

**Step 2 — First invest:** Alice calls `invest(1000 USDC, S)`:
- `_verifyInvestSignature(S)` passes — hash matches
- `position.investedCapital += 1000`
- No signature invalidation occurs

**Step 3 — Replay with different amount:** Alice calls `invest(5000 USDC, S)`:
- `_verifyInvestSignature(S)` passes again — same hash `(Alice, saleContract, chainId)`, unchanged
- `position.investedCapital += 5000` → total now 6000 USDC
- Alice invested 6x her intended allocation using the same signature

**Step 4 — Repeated replay:** Alice can continue calling `invest()` with any amount until the sale ends or capacity is reached.

**Root cause evidence — compare with PreLiquidApprovedSale:**

```solidity
// LegionPreLiquidApprovedSale.sol L1030-1050 — invest signatures ARE amount-bound
bytes32 _data = keccak256(abi.encodePacked(
    msg.sender, address(this), block.chainid,
    _investAmount, _tokenAllocationRate, _actionType  // ← amount IS included
)).toEthSignedMessageHash();

// L967-970 — signatures ARE tracked
function _verifySignatureNotUsed(bytes calldata _signature) private view {
    if (s_usedSignatures[msg.sender][_signature])
        revert Errors.LegionSale__SignatureAlreadyUsed(_signature);
}
```

The three affected contracts (`FixedPriceSale`, `SealedBidAuctionSale`, `PreLiquidOpenApplicationSale`) lack both protections.
