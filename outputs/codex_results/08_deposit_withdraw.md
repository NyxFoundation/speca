1 confirmed issue found.

1. **Medium: zero-mint deposit griefing (small deposits can be forced to fail)**
- Root cause:
  - [`reserve.move:160`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/reserve.move:160): `mint_amount = float::int_div(collateral_amount, self.exchange_rate())` (rounds down).
  - [`market.move:285`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/market.move:285): result used without explicit `mint_amount > 0` guard.
  - [`ctoken_table.move:68`](/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/sources/internal/market/ctoken_table.move:68): later aborts on zero cToken (`assert!(balance.value() > 0, ...)`).
- Attack path:
  1. Exchange rate rises (naturally from interest accrual or sustained tiny-share supply conditions).
  2. Victim deposits an amount `< exchange_rate`.
  3. `int_div` floors to `0` minted cTokens.
  4. Deposit reverts at `join_ctoken` zero-value assert.
- Impact:
  - No direct fund theft (transaction abort is atomic), but **reliable DoS/griefing on small deposits** once exchange rate is high enough.

Checked but **not confirmed exploitable** from provided code:
- First depositor inflation theft: no clear arbitrary donation path to force profitable vault inflation from these paths alone.
- Rounding direction (`int_mul`/`int_div`): both floor; conservative for protocol, no over-withdraw path found.
- Health check ordering in withdraw: collateral is reduced before check, but abort reverts state; no bypass found.
- Deposit-then-withdraw in same PTB: no profitable extraction path found; health check still enforced.