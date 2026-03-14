# PoC: Deposit Limit Double-Subtraction of cash_reserve — Limit Bypass

## Finding Reference
report_032_deposit_limit_double_subtraction

## Vulnerability
`deposit_limit_breached` subtracts `cash_reserve` twice:
1. Once implicitly via `total_deposit_plus_interest = exchange_rate * total_supply` where `exchange_rate = (debt + cash - cash_reserve) / total_supply`
2. Once explicitly: `total_deposit_plus_interest.ceil() + increment - cash_reserve.ceil() > limit`

Effective formula: `(debt + cash - cash_reserve) + increment - cash_reserve > limit`
Correct formula:  `(debt + cash - cash_reserve) + increment > limit`

Result: effective limit = `configured_limit + cash_reserve`

## Attack Cost
**Zero.** The depositor simply deposits normally. No special action required.

## Numerical Walkthrough

### Setup
```
Market: USDC (6 decimals)
Configured deposit_limit: 10,000,000 USDC
Reserve factor: 10%
```

### Step 1: Protocol Accumulates cash_reserve

cash_reserve grows from two sources:
1. Interest accrual: `reserve_factor × interest_accumulated` → `cash_reserve`
2. Flash loan fees: 100% of fee → `cash_reserve` via `increase_reserve_only()`

```
After 6 months of operation:
  Total borrows generated:  $50,000,000 cumulative
  Average interest:         8% APR × 6 months = 4%
  Interest accumulated:     $50,000,000 × 4% = $2,000,000
  Reserve factor:           10%
  cash_reserve from interest: $200,000

Flash loan activity:
  Total flash loan volume:  $500,000,000 cumulative
  Flash loan fee:           0.1%
  Flash loan fees:          $500,000
  All fees → cash_reserve:  $500,000

Total cash_reserve (before take_revenue): $700,000
```

### Step 2: Verify the Bug Arithmetically

```
Current state:
  cash         = 3,000,000
  debt         = 7,500,000
  cash_reserve = 700,000
  total_supply = 9,800,000 (cTokens)

exchange_rate = (debt + cash - cash_reserve) / total_supply
              = (7,500,000 + 3,000,000 - 700,000) / 9,800,000
              = 9,800,000 / 9,800,000
              = 1.0

total_deposit_plus_interest = exchange_rate × total_supply
                            = 1.0 × 9,800,000
                            = 9,800,000

BUGGY CHECK (actual code):
  total_deposit_plus_interest.ceil() + increment - cash_reserve.ceil() > limit
  9,800,000 + increment - 700,000 > 10,000,000
  increment > 10,000,000 - 9,800,000 + 700,000
  increment > 900,000

  → Can deposit up to 900,000 USDC before limit triggers

CORRECT CHECK (intended):
  total_deposit_plus_interest.ceil() + increment > limit
  9,800,000 + increment > 10,000,000
  increment > 200,000

  → Should only allow 200,000 USDC more

EXCESS DEPOSIT ALLOWED: 900,000 - 200,000 = 700,000 USDC = cash_reserve
```

### Step 3: Aggressive Scenario (High Flash Loan Volume)

Protocols with heavy flash loan activity accumulate large cash_reserve:

```
High-activity market (like a major USDC/ETH lending pool):
  Flash loan volume:       $2,000,000,000 cumulative
  Flash loan fee:          0.1%
  Flash loan fees:         $2,000,000

  Interest revenue:        $1,000,000
  Total cash_reserve:      $3,000,000

  Configured deposit_limit: $50,000,000

BUGGY: effective limit = $50,000,000 + $3,000,000 = $53,000,000
                          → 6% over intended limit

EXCESS DEPOSIT CAPACITY: $3,000,000
```

### Step 4: Impact Chain

```
1. Deposit limit exists to cap protocol risk exposure per asset
2. Bug allows deposits exceeding the limit by exactly cash_reserve
3. Excess deposits increase:
   - Utilization pressure (more cash available → more borrowing possible)
   - Protocol's aggregate exposure to that asset
   - Potential bad debt in a market crash

If asset drops 30% in a crash:
  Normal max exposure:  $50,000,000 → max bad debt risk proportional
  Actual exposure:      $53,000,000 → 6% more bad debt risk
  Extra bad debt risk:  $3,000,000 × bad_debt_rate
```

### Step 5: Deposit Limit vs cash_reserve Growth Over Time

| Protocol Age | cash_reserve | Configured Limit | Effective Limit | Bypass % |
|-------------|-------------|-----------------|----------------|----------|
| 1 month | $50,000 | $10,000,000 | $10,050,000 | 0.5% |
| 6 months | $700,000 | $10,000,000 | $10,700,000 | 7% |
| 1 year | $2,000,000 | $10,000,000 | $12,000,000 | 20% |
| 2 years | $5,000,000 | $10,000,000 | $15,000,000 | 50% |

cash_reserve monotonically increases unless admin calls `take_revenue()`. The bypass grows proportionally.

### Why take_revenue Doesn't Fully Mitigate

- `take_revenue` requires manual admin action (no auto-sweep)
- `take_revenue` itself has a bug (report_014: no interest accrual before withdrawal)
- Between admin sweeps, cash_reserve accumulates and the limit is inflated
- Governance latency means the limit bypass persists for extended periods

## Code References
- Bug location: `reserve.move:87-90` (`deposit_limit_breached`)
- `exchange_rate`: `reserve.move:92-101`
- `cash_plus_borrows_minus_reserves`: `reserve.move:74-76`
- `total_deposit_plus_interest`: `reserve.move:82-84`
- `increase_reserve_only` (flash loan fees → cash_reserve): `reserve.move:285-294`
- `accrue_interest` (interest → cash_reserve): `reserve.move:142-143`
- Deposit limit enforcement: `market.move:278` (`handle_mint`)

## Severity Justification
- **Attack cost: $0** — normal deposit, no special action
- **Bypass amount: equals cash_reserve** — grows monotonically with protocol usage
- **For mature protocols: 20-50% limit bypass is plausible**
- **Impact: undermines risk management** — excess deposits increase bad debt exposure
- **Severity: Medium** (systematic risk management bypass, grows over time, zero cost)

## Tool Used
Manual Review + Automated Analysis
