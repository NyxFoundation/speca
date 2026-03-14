Confirmed math/precision vulnerabilities I found:

1. **Medium: Liquidation protocol-fee bypass via floor rounding**
- Root cause: [`int_mul`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/math/sources/float.move:63) truncates down: `floor(rate * amount)`.
- Exploit path:
1. Liquidation fee for protocol is computed as `liq_revenue_factor.int_mul(redeem_collateral_amount)` in [`reserve.move`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:175).
2. Liquidation allows any non-zero repay amount in [`market.move`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:712).
3. An attacker splits liquidation into many small chunks so each chunk’s `protocol_seize_amount` rounds to `0`.
- Impact: Liquidator captures value that should go to protocol reserves; protocol liquidation revenue can be near-zero under chunked execution.

2. **Medium: Zero-mint deposit (silent donation) from truncating integer division**
- Root cause: [`int_div`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/math/sources/float.move:68) truncates down and can return `0` for positive input.
- Exploit path:
1. Deposit mint uses `mint_amount = float::int_div(collateral_amount, exchange_rate)` in [`reserve.move`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:160).
2. No check that `mint_amount > 0`; underlying is still deposited.
3. For small deposits when exchange rate is high, user gets `0` cTokens and loses funds.
- Impact: Irrecoverable user loss and value transfer to existing cToken holders; can be abused by malicious integrators/UIs to skim user dust.

3. **Low: Unchecked zero denominators in float division primitives (abort/DoS edge-case)**
- Root cause: no denominator guard in [`from_quotient`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/math/sources/float.move:21), [`int_div`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/math/sources/float.move:68), [`div`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/math/sources/float.move:83).
- Exploit path example: liquidation safety check computes `user_ltv = weighted_debts_value.div(collateral_total_value)` in [`market.move`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:966); if denominator hits zero in stressed/oracle-edge states, tx aborts.
- Impact: transaction-level DoS on critical flows (not direct fund theft, but can block liquidation progress).

4. **Low: `pow10_u64` hard-aborts for decimals > 18 (asset-level DoS risk)**
- Root cause: [`pow10_u64`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/math/sources/u64.move:6) aborts when `exp > 18`.
- Exploit path: math is used in liquidation sizing (`pow10_u64(coin_decimals)`) in [`market.move`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:1050). Any listed asset with metadata decimals >18 causes reverts in these paths.
- Impact: asset operations can become unusable (DoS) for such markets.

Notes on requested categories:
- **Intermediate overflow in `float.move` core ops**: I did not confirm a practical overflow in the current `u64`-bounded input model plus `VALUE_MAX_256` cap.
- **`u128.move`**: main arithmetic helpers (`mul_div`, `checked_mul`, `is_safe_mul`) are `#[test_only]`, so I did not count them as production exploitable issues.