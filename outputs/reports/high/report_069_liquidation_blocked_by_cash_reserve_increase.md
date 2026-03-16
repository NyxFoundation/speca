### Liquidation blocked by protocol fee inflating cash_reserve before withdrawal check in liquidate_ctokens

### Summary

In `reserve::liquidate_ctokens`, the protocol's `liquidation_fee_rate` cut (`protocol_seize_amount`) is added to `cash_reserve` **before** `withdraw_underlying` checks `cash >= cash_reserve.ceil()`. This eliminates a valid liquidation window where `free_cash < seize_amount <= free_cash + protocol_seize_amount`, blocking liquidations that would otherwise succeed. Blocked liquidations allow positions to deteriorate into bad debt, causing direct fund loss to depositors.

### Root Cause

In [`reserve.move:166-181`](contracts/protocol/sources/internal/market/reserve.move#L166-L181):

```move
public(package) fun liquidate_ctokens<MarketType, CoinType>(
    self: &mut Reserve<MarketType>,
    ctokens: Coin<CToken<MarketType, CoinType>>,
    liq_revenue_factor: Decimal,
): Balance<CoinType> {
    let redeem_collateral_amount = self.exchange_rate<MarketType>().int_mul(ctokens.value());
    let protocol_seize_amount = liq_revenue_factor.int_mul(redeem_collateral_amount);
    let liquidator_seize_amount = redeem_collateral_amount - protocol_seize_amount;

    // BUG: cash_reserve increased BEFORE withdraw check
    self.cash_reserve = self.cash_reserve.add(math::float::from(protocol_seize_amount));

    self.decrease_ctoken_supply(ctokens.into_balance());
    self.withdraw_underlying(liquidator_seize_amount)
}
```

And `withdraw_underlying` at [`reserve.move:306-316`](contracts/protocol/sources/internal/market/reserve.move#L306-L316):

```move
fun withdraw_underlying<MarketType, CoinType>(self: &mut Reserve<MarketType>, amount: u64): Balance<CoinType> {
    self.cash = self.cash - amount;
    assert!(self.cash >= self.cash_reserve.ceil(), error::market_cash_reserve_not_enough());
    reserve_token_balance.underlying_balance.split(amount)
}
```

**The math of the bug:**

Let `free = cash - ceil(cash_reserve)` (available cash beyond protocol reserves), `redeem = exchange_rate * ctokens` (total redeemed amount), `ps = protocol_seize_amount`.

After the check, `liquidator_seize = redeem - ps`. The remaining cash is `cash - liquidator_seize = cash - redeem + ps`.

- **Without bug** (check uses old `cash_reserve`): passes when `cash - redeem + ps >= ceil(cash_reserve)`, i.e., `free + ps >= redeem`.
- **With bug** (check uses new `cash_reserve + ps`): passes when `cash - redeem + ps >= ceil(cash_reserve + ps) = ceil(cash_reserve) + ps`, i.e., `free >= redeem`.

The bug eliminates the window `free < redeem <= free + ps`. In this window, the liquidation **should** succeed (the protocol's fee tokens stay in the reserve, effectively covering the gap) but **actually reverts**.

### Internal Pre-conditions

1. A collateral reserve needs to have moderate-to-high utilization such that `free_cash = cash - cash_reserve.ceil()` is small relative to the collateral being liquidated.
2. An obligation needs to be eligible for liquidation with collateral in that reserve.
3. `liquidation_fee_rate` needs to be > 0 (true for all normal liquidations; set in `AssetConfig`).

### External Pre-conditions

1. Price movement needs to make an obligation eligible for liquidation.

### Attack Path

1. USDC pool has: cash = 500K, debt = 4.5M, cash_reserve = 450K (ceil = 450K). Free cash = 50K. Exchange rate = (500K + 4.5M - 450K) / total_supply.
2. Borrower's ETH collateral drops in price. Their obligation becomes liquidatable.
3. Liquidator calculates seize of 55K USDC worth of ctokens from the USDC collateral reserve.
   - `redeem = 55K`. `protocol_seize = 5.5K` (10% fee). `liquidator_seize = 49.5K`.
4. **Without bug:** Check: `free + ps = 50K + 5.5K = 55.5K >= 55K = redeem`. **PASSES.** The 5.5K protocol fee stays in the reserve, covering the 5K deficit.
5. **With bug:** Check: `free = 50K >= 55K = redeem`. **FAILS.** The liquidation reverts.
6. The 5K gap (= redeem - free) cannot be liquidated. The obligation's bad exposure grows.
7. If the borrower's position continues deteriorating, the unliquidated portion becomes bad debt.
8. Depositors in the USDC pool lose funds proportional to the bad debt.

### Impact

Depositors in the collateral reserve suffer direct fund loss when liquidations that would reduce bad debt exposure are blocked. The blocked liquidation window is `protocol_seize_amount` tokens per liquidation attempt.

For a pool with:
- $5M total value, 90% utilization, $50K free cash
- 10% `liquidation_fee_rate`
- Liquidation attempt for $55K of collateral

The bug blocks $5.5K of liquidatable value per attempt. Over multiple attempts with deteriorating prices, the cumulative blocked amount compounds as the position's collateral value drops further. In a rapid price decline, the gap between the liquidatable amount (with bug) and the actual risk exposure can exceed 1% of pool value.

Loss exceeds $10 and 1% for pools with >$500K TVL under high-utilization stress conditions.

### PoC

**File:** `poc_069_liquidation_cash_reserve_block.move`

The PoC demonstrates the code path where `protocol_seize_amount` is added to `cash_reserve` before the withdrawal check. The key mathematical proof is:

```
Without bug: liquidation succeeds when free + protocol_seize >= redeem
With bug:    liquidation succeeds when free               >= redeem
Blocked window: free < redeem <= free + protocol_seize
```

### Mitigation

Move the `cash_reserve` increase to AFTER the `withdraw_underlying` call:

```move
public(package) fun liquidate_ctokens<MarketType, CoinType>(
    self: &mut Reserve<MarketType>,
    ctokens: Coin<CToken<MarketType, CoinType>>,
    liq_revenue_factor: Decimal,
): Balance<CoinType> {
    assert!(ctokens.value() > 0, error::reserve_zero_coin_not_allowed());

    let redeem_collateral_amount = self.exchange_rate<MarketType>().int_mul(ctokens.value());
    let protocol_seize_amount = liq_revenue_factor.int_mul(redeem_collateral_amount);
    let liquidator_seize_amount = redeem_collateral_amount - protocol_seize_amount;

    self.decrease_ctoken_supply(ctokens.into_balance());
    let result = self.withdraw_underlying(liquidator_seize_amount);

    // Move cash_reserve increase AFTER withdrawal
    self.cash_reserve = self.cash_reserve.add(math::float::from(protocol_seize_amount));

    result
}
```

This restores the valid liquidation window where `free < redeem <= free + protocol_seize`, allowing the protocol fee to effectively cover the cash deficit since those tokens remain in the reserve.
