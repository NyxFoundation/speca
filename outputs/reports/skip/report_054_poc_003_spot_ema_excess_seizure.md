# PoC: Liquidation Spot/EMA Price Inconsistency — Excess Collateral Extraction

## Finding Reference
report_003_liquidation_spot_vs_ema_price

## Vulnerability
- Liquidation **eligibility** check: uses `get_price()` → EMA price
- Seizure **amount** calculation: uses `get_spot_price()` → spot price
- Borrow/withdraw safety checks use `get_price_with_check()` → EMA + deviation guard (10% default)
- Liquidation path has **no deviation guard** between EMA and spot

## Attack Cost
**Zero.** The liquidator profits from normal liquidation. The excess extraction is pure additional profit at the borrower's expense with no extra capital risk.

## Numerical Walkthrough

### Setup
```
Token A (collateral): 9 decimals (like SUI)
Token B (debt):       6 decimals (like USDC)

eMode parameters:
  collateral_factor  = 0.80
  liquidation_factor = 0.85
  liquidation_incentive = 0.05 (5%)
  borrow_weight = 1.10
  close_factor = 0.50

Borrower's position:
  Collateral: 50,000 Token A
  Debt:       82,000 Token B (USDC)
```

### Step 1: Normal Market — No Divergence (baseline)
```
Token A: EMA = spot = $2.00
Token B: EMA = spot = $1.00

Collateral value    = 50,000 × $2.00 = $100,000
Weighted collateral = $100,000 × 0.85 = $85,000
Weighted debt       = 82,000 × $1.00 × 1.10 = $90,200

$90,200 > $85,000 → Liquidatable ✓

Liquidator repays 41,000 USDC (close_factor = 50%):
  seize = 41,000 × (1 + 0.05) × ($1.00 / $2.00) = 21,525 Token A
  Value = 21,525 × $2.00 = $43,050

  Liquidator profit = $43,050 - $41,000 = $2,050 (the 5% incentive)
  Borrower penalty  = $43,050 - $41,000 = $2,050
```

### Step 2: Market Crash — Spot Diverges from EMA
```
Token A suddenly drops 10%:
  EMA  = $2.00 (lagging, slow-moving average)
  Spot = $1.80 (immediate market price)

Token B: EMA = spot = $1.00 (stablecoin, no divergence)
```

### Step 3: Eligibility Check (uses EMA)
```
Collateral value (EMA) = 50,000 × $2.00 = $100,000
Weighted collateral    = $100,000 × 0.85 = $85,000
Weighted debt          = 82,000 × $1.00 × 1.10 = $90,200

$90,200 > $85,000 → Still liquidatable ✓
(Same as before — EMA hasn't moved)
```

### Step 4: Seizure Calculation (uses SPOT)
```
Liquidator repays 41,000 USDC:

  seize = repay × (1 + incentive) × price_debt_spot / price_collateral_spot
        = 41,000 × 1.05 × ($1.00 / $1.80)
        = 43,050 / 1.80
        = 23,916.67 Token A  (floor → 23,916)

  Value at EMA  = 23,916 × $2.00 = $47,832
  Value at spot = 23,916 × $1.80 = $43,048.80
```

### Step 5: Excess Extraction
```
Fair seizure (if both used EMA):
  = 41,000 × 1.05 × ($1.00 / $2.00) = 21,525 Token A

Actual seizure (spot price):
  = 23,916 Token A

EXCESS COLLATERAL SEIZED:
  = 23,916 - 21,525 = 2,391 Token A

VALUE OF EXCESS (at EMA):
  = 2,391 × $2.00 = $4,782

VALUE OF EXCESS (at spot):
  = 2,391 × $1.80 = $4,303.80
```

### Impact Summary
```
                        Normal      With 10% Divergence
Collateral seized       21,525      23,916 Token A
Liquidator profit       $2,050      $6,832 (EMA) / $2,048.80 (spot)
Excess extraction       —           $4,782 (EMA valuation)
Borrower extra loss     —           $4,782

Attack cost:            $0 (liquidation is profitable either way)
Profit ratio:           ∞ (no additional cost)
```

### Scaling to Larger Positions

| Position Size | 10% Divergence Excess | 5% Divergence Excess |
|---------------|----------------------|---------------------|
| $100,000 | $4,782 | $2,281 |
| $500,000 | $23,910 | $11,405 |
| $1,000,000 | $47,820 | $22,810 |
| $5,000,000 | $239,100 | $114,050 |

### Why the Deviation Guard Doesn't Help

The `DEFAULT_EMA_SPOT_DIFF_TOLERANCE_BPS = 1000` (10%) deviation guard is only applied in `get_price_with_check()`, which is used for:
- `collaterals_usd_non_liquidation()` (borrow/withdraw safety)
- `debts_value_usd_non_liquidation()` (borrow/withdraw safety)

It is **NOT** applied in:
- `debts_value_usd_for_liquidation()` → uses `get_price()` (plain EMA, no check)
- `collaterals_usd_for_liquidation()` → uses `get_price()` (plain EMA, no check)
- `liquidate_calculate_seize_ctokens()` → uses `get_spot_price()` (raw spot, no check)

The liquidation path operates in a completely unguarded price environment.

### Reverse Direction (Debt Token Spike)

If the debt token's spot price spikes while EMA lags:
```
Token B (debt): EMA = $1.00, spot = $1.10 (10% spike)
Token A (collateral): EMA = spot = $2.00

Seizure:
  = 41,000 × 1.05 × ($1.10 / $2.00) = 23,677.50 Token A

vs fair (EMA):
  = 41,000 × 1.05 × ($1.00 / $2.00) = 21,525 Token A

Excess = 2,152.5 Token A = $4,305
```

Both directions (collateral crash or debt spike) yield excess extraction.

## Code References
- Seizure uses spot: `market.move:1045-1046` (`get_spot_price`)
- Eligibility uses EMA: `market.move:1115,1155` (`get_price`)
- Non-liquidation uses EMA+check: `market.move:1198,1284` (`get_price_with_check`)
- Oracle functions: `user.move:26-59`
- Deviation tolerance: `market.move:30` (`DEFAULT_EMA_SPOT_DIFF_TOLERANCE_BPS = 1000`)

## Severity Justification
- **Attack cost: $0** — liquidator profits regardless
- **Excess extraction: ~$48K per $1M position at 10% divergence**
- **Frequency: every liquidation during volatile markets** (exactly when liquidations happen most)
- **No mitigation available to borrower** — cannot prevent liquidation or control which price is used
- **Severity: Medium** (consistent, material excess loss to borrowers with zero attack cost)

## Tool Used
Manual Review + Automated Analysis
