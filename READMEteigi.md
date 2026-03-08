# Current Finance contest details

- Join [Sherlock Discord](https://discord.gg/MABEWyASkp)
- Submit findings using the **Issues** page in your private contest repo (label issues as **Medium** or **High**)
- [Read for more details](https://docs.sherlock.xyz/audits/watsons)

# Q&A

### Q: On what chains are the smart contracts going to be deployed?
Sui
___

### Q: If you are integrating tokens, are you allowing only whitelisted tokens to work with the codebase or any complying with the standard? Are they assumed to have certain properties, e.g. be non-reentrant? Are there any types of [weird tokens](https://github.com/d-xo/weird-erc20) you want to integrate?
whitelisted token, LST, only the standard Sui Coin type is supported.

___

### Q: Are there any limitations on values set by admins (or other roles) in the codebase, including restrictions on array lengths?
Admin caps will be transferred to governance contract
___

### Q: Are there any limitations on values set by admins (or other roles) in protocols you integrate with, including restrictions on array lengths?
No
___

### Q: Is the codebase expected to comply with any specific EIPs?
No
___

### Q: Are there any off-chain mechanisms involved in the protocol (e.g., keeper bots, arbitrage bots, etc.)? We assume these mechanisms will not misbehave, delay, or go offline unless otherwise specified.
Liquidation bots, but SRs should assume it's possible for the position to not get liquidated on time and get into bad debt.

___

### Q: What properties/invariants do you want to hold even if breaking them has a low/unknown impact?
Lending protocol is based on exchange rate, ctoken and borrow index, so the invariants should apply to this lending protocol:

- Users cannot switch emode once obligations are created. 
- Only assets from the emode can be borrowed by an obligation.

All the above should always hold, as well as under flash loan with reentrancy, i.e. under flashloan and deposit/borrow in one ptb.

___

### Q: Please discuss any design choices you made.
Flashloan fees are tied to emode.
___

### Q: Please provide links to previous audits (if any) and all the known issues or acceptable risks.
Not public yet, but it was audited twice. All the known issues from these audits were fixed.
___

### Q: Additional audit information.
The contest has a conditional pot:
7,500 USDC is guaranteed
29,500 USDC is the full contest pot if High is found. In this case, the total rewards become 41,500 USDC, including LSW and LJ fixed pays.


# Audit scope

[sui-move-contract @ 8a250918a763b63449a767482a4c4a5079b30893](https://github.com/pebble-protocol/sui-move-contract/tree/8a250918a763b63449a767482a4c4a5079b30893)
- [sui-move-contract/contracts/math/sources/error.move](sui-move-contract/contracts/math/sources/error.move)
- [sui-move-contract/contracts/math/sources/float.move](sui-move-contract/contracts/math/sources/float.move)
- [sui-move-contract/contracts/math/sources/u128.move](sui-move-contract/contracts/math/sources/u128.move)
- [sui-move-contract/contracts/math/sources/u64.move](sui-move-contract/contracts/math/sources/u64.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/admin/adl.move](sui-move-contract/contracts/protocol/sources/entry_points/admin/adl.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/admin/asset.move](sui-move-contract/contracts/protocol/sources/entry_points/admin/asset.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/admin/decimal.move](sui-move-contract/contracts/protocol/sources/entry_points/admin/decimal.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/admin/emode.move](sui-move-contract/contracts/protocol/sources/entry_points/admin/emode.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/admin/liquidity_mining.move](sui-move-contract/contracts/protocol/sources/entry_points/admin/liquidity_mining.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/admin/market.move](sui-move-contract/contracts/protocol/sources/entry_points/admin/market.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/admin/referral.move](sui-move-contract/contracts/protocol/sources/entry_points/admin/referral.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/admin/revenue.move](sui-move-contract/contracts/protocol/sources/entry_points/admin/revenue.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/admin/version.move](sui-move-contract/contracts/protocol/sources/entry_points/admin/version.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/admin/whitelist.move](sui-move-contract/contracts/protocol/sources/entry_points/admin/whitelist.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/lending/borrow.move](sui-move-contract/contracts/protocol/sources/entry_points/lending/borrow.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/lending/deposit.move](sui-move-contract/contracts/protocol/sources/entry_points/lending/deposit.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/lending/enter_market.move](sui-move-contract/contracts/protocol/sources/entry_points/lending/enter_market.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/lending/flash_loan.move](sui-move-contract/contracts/protocol/sources/entry_points/lending/flash_loan.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/lending/liquidate.move](sui-move-contract/contracts/protocol/sources/entry_points/lending/liquidate.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/lending/liquidity_mining.move](sui-move-contract/contracts/protocol/sources/entry_points/lending/liquidity_mining.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/lending/repay.move](sui-move-contract/contracts/protocol/sources/entry_points/lending/repay.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/lending/withdraw.move](sui-move-contract/contracts/protocol/sources/entry_points/lending/withdraw.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/query/market_query.move](sui-move-contract/contracts/protocol/sources/entry_points/query/market_query.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/query/obligation_query.move](sui-move-contract/contracts/protocol/sources/entry_points/query/obligation_query.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/query/types.move](sui-move-contract/contracts/protocol/sources/entry_points/query/types.move)
- [sui-move-contract/contracts/protocol/sources/entry_points/referral.move](sui-move-contract/contracts/protocol/sources/entry_points/referral.move)
- [sui-move-contract/contracts/protocol/sources/internal/app.move](sui-move-contract/contracts/protocol/sources/internal/app.move)
- [sui-move-contract/contracts/protocol/sources/internal/coin_decimals_registry.move](sui-move-contract/contracts/protocol/sources/internal/coin_decimals_registry.move)
- [sui-move-contract/contracts/protocol/sources/internal/ctoken.move](sui-move-contract/contracts/protocol/sources/internal/ctoken.move)
- [sui-move-contract/contracts/protocol/sources/internal/error.move](sui-move-contract/contracts/protocol/sources/internal/error.move)
- [sui-move-contract/contracts/protocol/sources/internal/liquidity/liquidity_miner.move](sui-move-contract/contracts/protocol/sources/internal/liquidity/liquidity_miner.move)
- [sui-move-contract/contracts/protocol/sources/internal/liquidity/reward_manager.move](sui-move-contract/contracts/protocol/sources/internal/liquidity/reward_manager.move)
- [sui-move-contract/contracts/protocol/sources/internal/market/adl.move](sui-move-contract/contracts/protocol/sources/internal/market/adl.move)
- [sui-move-contract/contracts/protocol/sources/internal/market/asset.move](sui-move-contract/contracts/protocol/sources/internal/market/asset.move)
- [sui-move-contract/contracts/protocol/sources/internal/market/borrow_index.move](sui-move-contract/contracts/protocol/sources/internal/market/borrow_index.move)
- [sui-move-contract/contracts/protocol/sources/internal/market/ctoken_table.move](sui-move-contract/contracts/protocol/sources/internal/market/ctoken_table.move)
- [sui-move-contract/contracts/protocol/sources/internal/market/debt.move](sui-move-contract/contracts/protocol/sources/internal/market/debt.move)
- [sui-move-contract/contracts/protocol/sources/internal/market/emode.move](sui-move-contract/contracts/protocol/sources/internal/market/emode.move)
- [sui-move-contract/contracts/protocol/sources/internal/market/interest.move](sui-move-contract/contracts/protocol/sources/internal/market/interest.move)
- [sui-move-contract/contracts/protocol/sources/internal/market/limiter.move](sui-move-contract/contracts/protocol/sources/internal/market/limiter.move)
- [sui-move-contract/contracts/protocol/sources/internal/market/market.move](sui-move-contract/contracts/protocol/sources/internal/market/market.move)
- [sui-move-contract/contracts/protocol/sources/internal/market/obligation.move](sui-move-contract/contracts/protocol/sources/internal/market/obligation.move)
- [sui-move-contract/contracts/protocol/sources/internal/market/reserve.move](sui-move-contract/contracts/protocol/sources/internal/market/reserve.move)
- [sui-move-contract/contracts/protocol/sources/internal/market_type.move](sui-move-contract/contracts/protocol/sources/internal/market_type.move)
- [sui-move-contract/contracts/protocol/sources/internal/referral.move](sui-move-contract/contracts/protocol/sources/internal/referral.move)
- [sui-move-contract/contracts/protocol/sources/internal/store/generic_store.move](sui-move-contract/contracts/protocol/sources/internal/store/generic_store.move)
- [sui-move-contract/contracts/protocol/sources/internal/store/wit_table.move](sui-move-contract/contracts/protocol/sources/internal/store/wit_table.move)
- [sui-move-contract/contracts/protocol/sources/internal/value.move](sui-move-contract/contracts/protocol/sources/internal/value.move)
- [sui-move-contract/contracts/x_oracle/sources/entry_points/admin.move](sui-move-contract/contracts/x_oracle/sources/entry_points/admin.move)
- [sui-move-contract/contracts/x_oracle/sources/entry_points/user.move](sui-move-contract/contracts/x_oracle/sources/entry_points/user.move)
- [sui-move-contract/contracts/x_oracle/sources/internal/error.move](sui-move-contract/contracts/x_oracle/sources/internal/error.move)
- [sui-move-contract/contracts/x_oracle/sources/internal/price_feed.move](sui-move-contract/contracts/x_oracle/sources/internal/price_feed.move)
- [sui-move-contract/contracts/x_oracle/sources/internal/pyth_adaptor.move](sui-move-contract/contracts/x_oracle/sources/internal/pyth_adaptor.move)
- [sui-move-contract/contracts/x_oracle/sources/internal/x_oracle.move](sui-move-contract/contracts/x_oracle/sources/internal/x_oracle.move)


