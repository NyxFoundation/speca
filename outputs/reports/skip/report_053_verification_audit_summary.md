# Report Verification Audit Summary — Current Finance (Sherlock #1256)

## Tool Used
Manual Review + Automated Analysis (SPECA Pipeline Verification)

## Methodology
All 63 report files in `outputs/reports/` were verified against the target codebase at commit `8a250918a763b63449a767482a4c4a5079b30893` (pebble-protocol/sui-move-contract). Each report was checked for:
1. **Scope**: Referenced files must be within the 56 in-scope files defined in READMEteigi.md
2. **Code Validity**: Claims were verified by reading the actual source code at cited lines
3. **Severity**: Assessed against Sherlock guidelines (only Medium/High are valid submissions)
4. **Duplicates**: Cross-checked against other reports for overlapping findings

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Total Reports Verified | 63 |
| VALID (Medium+) | 18 |
| VALID (Low — below Sherlock threshold) | 14 |
| VALID (Informational/QA) | 3 |
| INVALID | 27 |
| DUPLICATE | 1 |

---

## VALID Reports — Medium Severity (Sherlock-Submittable)

| # | Report File | Title | Severity |
|---|-------------|-------|----------|
| 1 | report_003 | Liquidation uses spot price for seizure but EMA for eligibility — excess collateral extraction | Medium |
| 2 | report_004 | ADL borrow activation uses global debt instead of emode-specific — unfair liquidation | Medium |
| 3 | report_007 | `burn_whitelist` lacks AdminCap check — cap holder can self-destruct | Medium |
| 4 | report_009 | Oracle deviation check asymmetric — division by spot underestimates upward divergence | Medium |
| 5 | report_029 | Liquidation only checks collateral asset pause, not debt asset — incomplete pause | Medium |
| 6 | report_031 | Circuit break blocks ALL liquidation including ADL — bad debt accumulation | Medium |
| 7 | report_032 | Deposit limit check double-subtracts `cash_reserve` — allows limit bypass | Medium |
| 8 | report_035 (ADL LTV) | ADL LTV degrades to zero via `saturating_sub` — all positions liquidatable | Medium |
| 9 | report_036 (min borrow) | Liquidation skips `min_borrow_amount` check — creates unclearable dust positions | Medium |
| 10 | report_038 (zero collateral) | ADL division-by-zero abort on zero-collateral obligations | Medium |
| 11 | report_041 | `deposit_limit_breached` u64 underflow blocks all deposits | Medium |
| 12 | report_044 (liquidation limiter) | Liquidation repay does not reduce borrow rate-limiter — artificial saturation | Medium |
| 13 | report_044 (non-collateral) | Non-collateral interest skip on withdraw — stale exchange rate | Medium |
| 14 | report_048 (close factor) | Close factor bypass via per-debt-type threshold — full liquidation possible | Medium |
| 15 | report_049 (liquidity mining) | Pool close griefing by unclaimed obligation trackers | Medium |
| 16 | report_049 (emode stale) | eMode borrow tracking uses stale debt in repay/liquidation — upward drift | Medium |
| 17 | report_050 | Flash loan fees bypass `reserve_factor` split — depositors get nothing | Medium |
| 18 | report_052 | Non-collateral withdraw blocked by unrelated oracle staleness (code has TODO) | Medium |

---

## VALID Reports — Low Severity (Below Sherlock Medium Threshold)

| # | Report File | Title | Assessed Severity |
|---|-------------|-------|-------------------|
| 1 | report_014 | `take_revenue` does not accrue interest before withdrawal | Low |
| 2 | report_018 | Flash loan fee arbitrage across emode groups (whitelisted only) | Low |
| 3 | report_020 | Zero-mint deposit griefing via truncating division (extreme preconditions) | Low |
| 4 | report_021 | Cross-segment limiter reduction only affects current segment | Low |
| 5 | report_025 | Admin emode update resets rate limiter state | Low |
| 6 | report_028 (dust) | Dust obligations become unliquidatable (seize floors to zero) | Low |
| 7 | report_033 | Zero-share reward loss (intentional per test code) | Low |
| 8 | report_034 | Borrow reward share staleness (~0.8% advantage over 30 days) | Low |
| 9 | report_035 (pyth) | Pyth normalize_decimals truncation (unlikely precondition: >9 decimals) | Low |
| 10 | report_036 (flash loan) | Flash loan stale cash accounting (hot potato pattern limits exploit) | Low |
| 11 | report_038 (timestamp) | ADL cancel_collateral emits milliseconds instead of seconds | Low |
| 12 | report_039 | ADL bypasses liquidation pause (admin-controlled mechanism) | Low |
| 13 | report_047 | Referral discount parameters sum unbounded (admin misconfiguration) | Low |
| 14 | report_051 | Zero oracle delay tolerance bricks price checks (admin misconfiguration) | Low |

---

## VALID Reports — Informational/QA

| # | Report File | Title |
|---|-------------|-------|
| 1 | report_023 | Borrow off-by-one (`>` instead of `>=`) — 1 unit lock, standard DeFi pattern |
| 2 | report_048 (referral) | Referral code generation collision DoS — 2.18B namespace, negligible probability |
| 3 | report_049 (oracle admin) | Oracle admin timestamp unit inconsistency — off-chain only |

---

## INVALID Reports — Detailed Reasoning

| # | Report File | Reason for Invalidation |
|---|-------------|------------------------|
| 1 | report_001 | ADL borrow IS designed to seize collateral; report assumes non-existent design intent |
| 2 | report_002 | Static close factor is standard DeFi design (Compound, Aave); not a bug |
| 3 | report_005 | Lazy interest accrual tradeoff; effect is undercounting (more permissive), self-correcting |
| 4 | report_006 | Referral qualification explicitly designed for flash loan volume; deposit path has no referral tracking |
| 5 | report_008 | Intentional design — `// NOTE: disable rate limit` comment; blocking liquidation = bad debt |
| 6 | report_010 | Flash loan deposit-withdraw cycle nets to zero outflow change; health check prevents extraction |
| 7 | report_011 | Gas costs far exceed dust-amount protocol fee savings; not economically exploitable |
| 8 | report_012 | Zero-second interest is mathematically correct (0 time = 0 interest); standard in all DeFi |
| 9 | report_013 | `key, store` on PackageCallerCap is standard Sui Move convention for package capabilities |
| 10 | report_015 | Centralization / admin trust risk, not a code vulnerability |
| 11 | report_016 | Per-asset token-denominated limits are industry standard; each limiter is independent |
| 12 | report_017 | Invariant `cash >= cash_reserve` enforced in `withdraw_underlying` prevents util > 1.0 |
| 13 | report_019 | Self-referral via multiple addresses is inherent blockchain property, not code-specific |
| 14 | report_022 | Default 5s staleness is tight; 30-min max is admin-configurable trusted setting |
| 15 | report_024 | Simple interest is Compound v2 standard; report self-acknowledges this is known trade-off |
| 16 | report_026 | Blocking operations without valid oracle prices is by-design safety, not a vulnerability |
| 17 | report_027 | Intentional protocol-favoring rounding, acknowledged in code comments ("almost negligible") |
| 18 | report_028 (decimals) | `register_decimals` requires AdminCap; no external attack vector |
| 19 | report_030 | Report misunderstands control flow; trigger and stop are different code paths, not oscillating |
| 20 | report_037 (borrow stale) | Intentional design with explicit comment: "obligation owner can borrow a bit more" |
| 21 | report_037 (reward dust) | Impact miscalculated by confusing token units; actual loss is sub-cent, not ~1000 USDC |
| 22 | report_040 (circuit break) | Standard emergency pattern; interest doesn't auto-accrue in Move when all ops are blocked |
| 23 | report_042 | Post-liquidation health check not required; close factor limits damage; standard DeFi design |
| 24 | report_043 | Phantom debt from rounding is < 10^-18 per accrual; economically negligible |
| 25 | report_045 | ADL incentive is intentional to motivate operators; capped by normal liquidation incentive |
| 26 | report_040 (emode removal) | No admin entry point exists to remove asset from eMode group; `onboard_asset_to_emode_group` and `update_asset_in_emode_group` exist but no removal function — entire premise is fabricated |
| 27 | report_046 | `float::mul` and `float::div` both truncate DOWN (floor division); sum of truncated increments ≤ total, so `allocated_rewards` can never exceed `total_rewards` — underflow is mathematically impossible |

---

## DUPLICATE Report

| Report File | Duplicate Of | Reason |
|-------------|-------------|--------|
| report_039_adl_bypasses_liquidation_paused | report_039_adl_bypasses_liquidation_pause_control | Identical vulnerability description, same code references (market.move:519-520, 546-611, 613-677) |

---

## Key Findings by Attack Surface

### Liquidation Logic (7 findings)
- **report_003** (Medium): Spot/EMA price inconsistency in seizure calculation
- **report_029** (Medium): Missing debt asset pause check
- **report_031** (Medium): Circuit break blocks all liquidation
- **report_036b** (Medium): Missing min_borrow_amount check creates dust
- **report_044** (Medium): Limiter not reduced on liquidation repay
- **report_048** (Medium): Close factor bypass via per-debt-type threshold
- **report_009** (Medium): Asymmetric oracle deviation enables operations during dangerous divergence

### ADL (Auto-Deleverage) (3 findings)
- **report_004** (Medium): Global vs emode-specific debt check mismatch
- **report_035** (Medium): LTV degrades to zero over time
- **report_038** (Medium): Division-by-zero on zero-collateral positions

### Rate Limiter / Deposit Limits (2 findings)
- **report_032** (Medium): Double-subtraction of cash_reserve in deposit limit
- **report_041** (Medium): u64 underflow blocks deposits

### Interest / Exchange Rate (2 findings)
- **report_044b** (Medium): Non-collateral interest skip on withdraw
- **report_049b** (Medium): Stale eMode borrow tracking in repay/liquidation

### Liquidity Mining / Rewards (1 finding)
- **report_049a** (Medium): Pool close griefing by unclaimed obligations

### Oracle (1 finding)
- **report_052** (Medium): Non-collateral withdraw blocked by unrelated oracle (has TODO in code)

### Flash Loan / Referral (1 finding)
- **report_050** (Medium): Flash loan fees bypass reserve_factor — depositors uncompensated

### Access Control (1 finding)
- **report_007** (Medium): burn_whitelist lacks AdminCap check

---

## Recommendation

Of the 18 Medium-severity valid findings, the highest-impact for Sherlock submission are:
1. **report_003**: Exploitable by any liquidator, direct excess collateral extraction
2. **report_032**: Allows deposit limits to be bypassed by cash_reserve amount
3. **report_052**: User funds locked by unrelated oracle (devs acknowledged with TODO)
4. **report_041**: Complete deposit DoS under plausible conditions
5. **report_048**: Close factor protection fully bypassable for multi-debt obligations
