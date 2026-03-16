After thorough analysis of the deposit cap mechanism, I've verified all code paths:

**Deposit cap enforcement** (`market.move:277-283`):
- Only one entry point: `deposit.move:deposit()` → `market.handle_mint()`
- Cap check happens before ctoken minting (line 278 vs 285)
- `mint_ctokens` is only called from `handle_mint` — no alternative mint paths

**Race condition analysis**:
- On Sui, all operations on the same shared object (`Market`) are sequentially ordered — true race conditions are structurally impossible
- No concurrent deposit can bypass the cap

**Alternative deposit paths**:
- Liquidation (`liquidation_inner`): seizes existing ctokens, never mints new ones — doesn't bypass deposit cap
- Flash loans: use `borrow_flash_loan`/`repay_flash_loan` which don't mint ctokens — fees go to `cash_reserve` via `increase_reserve_only`
- No other path calls `mint_ctokens` or `increase_ctoken_supply`

**Limiter analysis**:
- `deposit_limiter` is actually a **withdrawal rate limiter** (deposits call `reduce_outflow`, withdrawals call `add_outflow`) — working as designed
- `count_current_outflow` segment tracking is correct for the circular buffer pattern
- `reduce_outflow` floors at 0 (safe, can't underflow)

**Already-known bugs covering this area**:
- `032:deposit_limit_double_subtract` — the `cash_reserve` double-subtraction in `deposit_limit_breached` formula
- `041:deposit_limit_underflow` — underflow in deposit limit

NO_NEW_FINDINGS: The deposit cap mechanism is structurally race-condition-free due to Sui's shared object ordering. The only deposit limit bugs (double-subtract of cash_reserve, potential underflow) are already known as bugs 032 and 041. No alternative deposit paths bypass the cap check.
