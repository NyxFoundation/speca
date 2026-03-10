# PoC: Close Factor Bypass via Per-Debt-Type Threshold Check

## Finding Reference
report_048_close_factor_bypass_per_debt_type

## Vulnerability
`ensure_liquidate_borrow_allowed` checks `close_factor_bypass_min_value` against the USD value of each **individual debt type**, not the total obligation debt. A liquidator calls `liquidate()` N times in a single PTB — once per debt type — each bypassing the close factor individually.

## Attack Cost
**Zero additional cost.** The liquidator profits from every liquidation call via the liquidation incentive. The extra liquidation beyond what close_factor allows generates **additional** profit for the liquidator at the borrower's expense.

## Numerical Walkthrough

### Setup
```
Market configuration:
  close_factor                   = 0.50 (50%)
  close_factor_bypass_min_value  = 5,000 USD
  liquidation_incentive          = 0.05 (5%)
  collateral_factor              = 0.80
  liquidation_factor             = 0.85
  borrow_weight                  = 1.10

Borrower's obligation:
  Collateral: 30,000 USDC worth of Token A (at $2.00 each = 15,000 Token A)

  Debts (5 different tokens, each in the same eMode group):
    Token B: $4,900 (just below $5,000 threshold)
    Token C: $4,900
    Token D: $4,900
    Token E: $4,900
    Token F: $4,900
    ─────────────────
    Total debt: $24,500

All token prices: EMA = spot = stable (no divergence needed)
```

### Step 1: Verify Position is Liquidatable
```
Collateral value       = $30,000
Weighted collateral    = $30,000 × 0.85 = $25,500
Weighted debt          = $24,500 × 1.10 = $26,950

$26,950 > $25,500 → Liquidatable ✓
```

### Step 2: Expected Behavior (Close Factor Enforced)
```
With close_factor = 50%, liquidator should only repay:
  max_repay_per_type = debt_balance × close_factor
  Token B: $4,900 × 0.50 = $2,450
  Token C: $4,900 × 0.50 = $2,450
  Token D: $4,900 × 0.50 = $2,450
  Token E: $4,900 × 0.50 = $2,450
  Token F: $4,900 × 0.50 = $2,450
  ─────────────────────────────────
  Max total repay: $12,250 (50% of $24,500)

Collateral seized = $12,250 × (1 + 0.05) = $12,862.50
Remaining collateral = $30,000 - $12,862.50 = $17,137.50
Remaining debt = $24,500 - $12,250 = $12,250

Position post-liquidation (intended):
  Weighted collateral = $17,137.50 × 0.85 = $14,566.88
  Weighted debt       = $12,250 × 1.10    = $13,475
  → Position is healthier, borrower retains $17,137.50 collateral
```

### Step 3: Actual Behavior (Close Factor Bypassed)
```
Each debt type's USD value:
  Token B: $4,900 ≤ $5,000 (close_factor_bypass_min_value) → BYPASS ✓
  Token C: $4,900 ≤ $5,000 → BYPASS ✓
  Token D: $4,900 ≤ $5,000 → BYPASS ✓
  Token E: $4,900 ≤ $5,000 → BYPASS ✓
  Token F: $4,900 ≤ $5,000 → BYPASS ✓

Liquidator calls liquidate() 5 times in a single PTB:

  Call 1: Repay ALL of Token B = $4,900 (100%, no close_factor limit)
    Seize: $4,900 × 1.05 = $5,145 collateral

  Call 2: Repay ALL of Token C = $4,900
    Seize: $4,900 × 1.05 = $5,145 collateral

  Call 3: Repay ALL of Token D = $4,900
    Seize: $4,900 × 1.05 = $5,145 collateral

  Call 4: Repay ALL of Token E = $4,900
    Seize: $4,900 × 1.05 = $5,145 collateral

  Call 5: Repay ALL of Token F = $4,900
    Seize: $4,900 × 1.05 = $5,145 collateral

Total repaid: $24,500 (100% of all debt — NOT 50%)
Total seized: $25,725 collateral

Remaining collateral: $30,000 - $25,725 = $4,275
Remaining debt: $0
```

### Step 4: Impact Comparison

```
                     Close Factor Enforced    Close Factor Bypassed
Total repaid         $12,250 (50%)            $24,500 (100%)
Collateral seized    $12,862.50               $25,725
Borrower retains     $17,137.50               $4,275
Excess penalty       —                        $12,862.50

EXCESS COLLATERAL LOSS TO BORROWER: $12,862.50
(= the additional 50% liquidation × 1.05 incentive)
```

### Step 5: Scaling Analysis

The attack scales with the number of debt types and position size. The key constraint is each debt type must be below `close_factor_bypass_min_value`.

| # Debt Types | Value Per Type | Total Debt | Close Factor (50%) Max | Actual (Bypassed) | Excess Penalty |
|-------------|---------------|-----------|----------------------|------------------|----------------|
| 3 | $4,900 | $14,700 | $7,350 | $14,700 | $7,717.50 |
| 5 | $4,900 | $24,500 | $12,250 | $24,500 | $12,862.50 |
| 8 | $4,900 | $39,200 | $19,600 | $39,200 | $20,580 |
| 10 | $4,900 | $49,000 | $24,500 | $49,000 | $25,725 |

### Step 6: Borrower Cannot Defend

The borrower has no defense mechanism:
1. Cannot prevent multi-type borrowing (protocol allows it by design)
2. Cannot prevent a liquidator from making multiple calls in one PTB
3. The close_factor is meant to protect borrowers from excessive one-shot liquidation
4. The per-type check completely nullifies this protection for diversified borrowers

### Step 7: Single-PTB Execution Proof

On Sui, a Programmable Transaction Block (PTB) executes atomically:
```
PTB {
  // All 5 calls share the same obligation and market objects
  liquidate<Market, TokenB, TokenA>(obligation, market, coin_b, ...);
  liquidate<Market, TokenC, TokenA>(obligation, market, coin_c, ...);
  liquidate<Market, TokenD, TokenA>(obligation, market, coin_d, ...);
  liquidate<Market, TokenE, TokenA>(obligation, market, coin_e, ...);
  liquidate<Market, TokenF, TokenA>(obligation, market, coin_f, ...);
}
```

Each call updates the obligation state before the next call sees it. After call 1 removes Token B debt, call 2 sees fewer debts. The position may become healthy after the first few calls, but `ensure_liquidate_borrow_allowed` re-checks eligibility per call. However, since each call reduces both debt AND collateral, the health ratio may remain unhealthy throughout — especially when the liquidation incentive means the seized collateral value exceeds the repaid debt value.

## Code References
- Per-type check: `market.move:1000-1006` (`debt_value <= close_factor_bypass_min_value`)
- `debt_value` is per-type: `market.move:998` (`obligation.debt(target_debt_type).unsafe_debt_amount()`)
- Close factor enforcement: `market.move:1008-1013`
- No per-PTB call limit: `liquidate.move:133-202`
- Entry point takes generic `DebtType`: `liquidate.move:133` (different type params per call)

## Severity Justification
- **Attack cost: $0** — liquidator profits from every call via 5% incentive
- **Excess collateral loss: up to 50% of total debt × (1 + incentive)** for diversified positions
- **Concrete: $12,862 excess loss on $24,500 debt (52.5% of debt value)**
- **Precondition: borrower has multiple debt types each below bypass threshold** — realistic for diversified borrowers
- **Severity: Medium** (systematic close factor bypass for multi-debt obligations)

## Tool Used
Manual Review + Automated Analysis
