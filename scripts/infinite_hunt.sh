#!/usr/bin/env bash
# ============================================================
# infinite_hunt.sh — 無限HIGHバグハンティングスクリプト
#
# レートリミットに当たったら自動で待機→復活後に再開
# 各ラウンドで異なるアングル/戦略で探索
# 発見→レポート→POC→コミット→プッシュ→Issue更新 を自動化
#
# Usage:
#   bash scripts/infinite_hunt.sh
#   bash scripts/infinite_hunt.sh --dry-run
# ============================================================

set -uo pipefail  # no -e: we handle errors ourselves

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

AUDIT_TARGET="C:/Users/shieru_k/Desktop/audit-current-main"
BRANCH="hiro/high-bug-hunting"
LOG_DIR="$REPO_ROOT/outputs/logs/hunt"
FINDINGS_DIR="$REPO_ROOT/outputs/hunt_findings"
STATE_FILE="$REPO_ROOT/outputs/hunt_state.txt"
DRY_RUN="${1:-}"

mkdir -p "$LOG_DIR" "$FINDINGS_DIR"

# ============================================================
# 探索戦略ローテーション
# ============================================================
STRATEGIES=(
  "exchange_rate_manipulation"
  "interest_accrual_edge_cases"
  "liquidation_incentive_overflow"
  "flash_loan_state_inconsistency"
  "oracle_price_staleness_window"
  "cross_function_reentrancy"
  "rounding_direction_attacks"
  "emode_isolation_bypass"
  "reserve_accounting_mismatch"
  "debt_token_rebasing"
  "ctoken_supply_inflation"
  "withdraw_before_accrue"
  "borrow_index_manipulation"
  "limiter_bypass_via_splitting"
  "adl_threshold_gaming"
  "multi_market_arbitrage"
  "obligation_state_desync"
  "flash_loan_fee_evasion"
  "deposit_cap_race_condition"
  "liquidation_sandwich"
  "bad_debt_amplification"
  "price_feed_front_running"
  "collateral_factor_boundary"
  "min_borrow_dust_attack"
  "repay_overflow_edge"
  "ctoken_exchange_rate_donation"
  "emode_group_migration_bug"
  "circuit_breaker_timing"
  "reward_pool_draining"
  "referral_rebate_overflow"
)

KNOWN_BUGS="003:spot_ema_price_inconsistency
048:close_factor_bypass_per_debt
062:bad_debt_not_socialized
009:oracle_deviation_asymmetric
031:circuit_break_blocks_liquidation
033:liquidity_mining_zero_share
036:liquidation_min_borrow
044:non_collateral_interest_skip
052:non_collateral_withdraw_oracle
004:adl_global_debt_check
025:admin_emode_resets_limiter
028:dust_obligation_unliquidatable
032:deposit_limit_double_subtract
034:borrow_reward_staleness
035:adl_ltv_degrades
038:adl_zero_collateral_div
039:adl_bypasses_pause
041:deposit_limit_underflow
049a:emode_stale_borrow
049b:liquidity_mining_grief
050:flash_loan_fee_bypass_reserve
057:repay_fee_rate_misused"

# ============================================================
# Pure bash ヘルパー (Python不要)
# ============================================================

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

get_round() {
  if [[ -f "$STATE_FILE" ]]; then
    grep "^round=" "$STATE_FILE" 2>/dev/null | cut -d= -f2 || echo 0
  else
    echo 0
  fi
}

save_state() {
  local round="$1"
  local strategy="$2"
  local status="$3"
  cat > "$STATE_FILE" <<STATEEOF
round=$round
strategy=$strategy
status=$status
last_update=$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S')
STATEEOF
}

# ============================================================
# プロンプト生成
# ============================================================

generate_prompt() {
  local strategy="$1"
  local round="$2"

  cat <<PROMPT
You are an elite DeFi security researcher specializing in lending protocol vulnerabilities.
Your mission: find NEW HIGH severity bugs in the Current Finance Sui Move lending protocol.

## Target
Audit target codebase: $AUDIT_TARGET
This is a Sui Move lending protocol (similar to Compound/Aave but on Sui blockchain).

## Strategy for this round: $strategy (Round #$round)

## ALREADY KNOWN BUGS — DO NOT DUPLICATE
$KNOWN_BUGS

## Sherlock HIGH criteria
- Direct fund loss >1% AND >\$10 for affected users
- No admin/owner action required as precondition
- Entry point must be a public/external function callable by anyone
- No chain-specific impossibilities (e.g., front-running on Sui is structurally difficult)

## Key source files to analyze
Focus on these based on strategy "$strategy":
- contracts/protocol/sources/internal/market/market.move (core: borrow, repay, liquidation, solvency checks)
- contracts/protocol/sources/internal/market/reserve.move (exchange rate, interest accrual, ctoken mint/burn)
- contracts/protocol/sources/internal/market/interest.move (tri-kink rate model)
- contracts/protocol/sources/internal/market/obligation.move (debt/collateral tracking)
- contracts/protocol/sources/internal/market/debt.move (debt accrual with borrow index)
- contracts/protocol/sources/internal/market/emode.move (isolated mode groups)
- contracts/protocol/sources/internal/market/limiter.move (rate limiting)
- contracts/protocol/sources/internal/market/adl.move (auto-deleverage)
- contracts/protocol/sources/entry_points/lending/*.move (all entry points)
- contracts/x_oracle/sources/**/*.move (oracle)
- contracts/math/sources/float.move (18-decimal fixed-point)

## Instructions
1. Read the relevant source code files for strategy "$strategy"
2. Think deeply about edge cases, boundary conditions, state transitions
3. Look for bugs that are NOT in the known list above
4. For each potential finding:
   a. Verify it is a REAL bug by tracing the exact code path
   b. Verify it meets Sherlock HIGH criteria
   c. Write a full report following this template:
      ### Title
      {actor} will {impact} {affected party}
      ### Summary
      {root cause} will cause {impact} for {affected party} as {actor} will {attack path}
      ### Root Cause
      In {link to code} the {root cause}
      ### Internal Pre-conditions
      (numbered list)
      ### External Pre-conditions
      (numbered list)
      ### Attack Path
      (numbered list of steps)
      ### Impact
      The {affected party} suffers approximate loss of {value}.
      ### PoC
      Write a complete Move test file. The test MUST PASS when the attack succeeds.
      ### Mitigation
      (fix suggestion)

5. Save the report to: $REPO_ROOT/outputs/reports/high/report_{NNN}_{slug}.md
6. Save the PoC to: $REPO_ROOT/outputs/pocs/poc_{NNN}_{slug}.move
   Use the next available number after 062.

If you find NOTHING new after thorough analysis, output exactly:
"NO_NEW_FINDINGS: [brief reason why this angle is exhausted]"

IMPORTANT: Only report findings you are CONFIDENT are real bugs. Do not report design decisions or known issues. Quality over quantity.
PROMPT
}

# ============================================================
# レートリミット検出 & 待機
# ============================================================

wait_for_rate_limit() {
  local wait_secs="${1:-300}"
  local max_wait=3600
  local attempt=0

  while true; do
    attempt=$((attempt + 1))
    local current_wait=$((wait_secs * attempt))
    if [[ $current_wait -gt $max_wait ]]; then
      current_wait=$max_wait
    fi

    log "Rate limit hit. Waiting ${current_wait}s (attempt #$attempt)..."
    save_state "$(get_round)" "waiting" "rate_limited"
    sleep "$current_wait"

    log "Testing if rate limit has recovered..."
    local test_result=""
    test_result=$(echo "Reply with exactly the word OK and nothing else" | timeout 60 claude --print 2>&1) || true

    if echo "$test_result" | grep -qi "OK"; then
      log "Rate limit recovered! Resuming..."
      return 0
    elif echo "$test_result" | grep -qi "rate\|limit\|429\|overloaded\|capacity"; then
      log "Still rate limited..."
      continue
    else
      log "Got response, assuming recovered"
      return 0
    fi
  done
}

# ============================================================
# 1ラウンド実行
# ============================================================

run_hunt_round() {
  local round="$1"
  local strategy_idx=$(( round % ${#STRATEGIES[@]} ))
  local strategy="${STRATEGIES[$strategy_idx]}"
  local timestamp=$(date '+%Y%m%d_%H%M%S')
  local log_file="$LOG_DIR/hunt_r${round}_${strategy}_${timestamp}.log"

  log "========================================="
  log "Round #$round — Strategy: $strategy"
  log "========================================="

  save_state "$round" "$strategy" "running"

  local prompt
  prompt=$(generate_prompt "$strategy" "$round")

  if [[ "$DRY_RUN" == "--dry-run" ]]; then
    log "[DRY RUN] Would execute claude with strategy: $strategy"
    echo "$prompt" > "$LOG_DIR/prompt_r${round}_${strategy}.txt"
    return 0
  fi

  local exit_code=0
  local output_file="$FINDINGS_DIR/round_${round}_${strategy}_${timestamp}.md"

  echo "$prompt" | timeout 1800 claude \
    --print \
    --allowed-tools "Read,Glob,Grep,Write" \
    --add-dir "$AUDIT_TARGET" \
    --permission-mode bypassPermissions \
    --max-budget-usd 5 \
    > "$output_file" 2>"$log_file" || exit_code=$?

  # レートリミットチェック
  if [[ $exit_code -ne 0 ]]; then
    local log_content=""
    log_content=$(cat "$log_file" "$output_file" 2>/dev/null) || true

    if echo "$log_content" | grep -qi "rate\|limit\|429\|overloaded\|capacity"; then
      log "Rate limit detected in round #$round"
      save_state "$round" "$strategy" "rate_limited"
      return 2
    elif echo "$log_content" | grep -qi "timeout\|timed out"; then
      log "Timeout in round #$round — moving to next strategy"
      save_state "$round" "$strategy" "timeout"
      return 0
    else
      log "Error in round #$round (exit=$exit_code) — continuing"
      save_state "$round" "$strategy" "error"
      return 0
    fi
  fi

  # 結果解析
  if grep -q "NO_NEW_FINDINGS" "$output_file" 2>/dev/null; then
    log "No new findings in round #$round ($strategy)"
    save_state "$round" "$strategy" "no_findings"
    return 0
  fi

  # 新しいレポート/PoCファイルがあるか
  local new_reports=0
  new_reports=$(git status --porcelain outputs/reports/high/ outputs/pocs/ 2>/dev/null | grep -c "^??" || true)

  if [[ "$new_reports" -gt 0 ]]; then
    log "*** NEW FINDING(S) in round #$round! ($new_reports new files) ***"
    save_state "$round" "$strategy" "found"

    git add outputs/reports/high/ outputs/pocs/ 2>/dev/null || true
    git add outputs/hunt_findings/ 2>/dev/null || true

    git commit -m "feat: HIGH bug hunt round #$round ($strategy) — new finding(s)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>" 2>/dev/null || true

    git push origin "$BRANCH" 2>/dev/null || true
    log "Committed and pushed new findings"
  else
    log "Round #$round completed — no new report files created"
    save_state "$round" "$strategy" "completed"
  fi

  return 0
}

# ============================================================
# メインループ
# ============================================================

main() {
  log "============================================"
  log " Infinite HIGH Bug Hunter — Starting"
  log " Target: $AUDIT_TARGET"
  log " Branch: $BRANCH"
  log " Strategies: ${#STRATEGIES[@]}"
  log "============================================"

  local round
  round=$(get_round)

  while true; do
    round=$((round + 1))

    local result=0
    run_hunt_round "$round" || result=$?

    if [[ $result -eq 2 ]]; then
      wait_for_rate_limit 300
      round=$((round - 1))
      continue
    fi

    if [[ $((round % ${#STRATEGIES[@]})) -eq 0 ]]; then
      log "=== Full strategy rotation complete (${#STRATEGIES[@]} strategies) ==="
      log "=== Starting next rotation with deeper analysis ==="
    fi

    sleep 5
  done
}

# ============================================================
# シグナルハンドラ
# ============================================================

cleanup() {
  log "Interrupted! Saving state..."
  save_state "$(get_round)" "interrupted" "stopped" 2>/dev/null || true
  log "State saved. Exiting."
  exit 0
}

trap cleanup SIGINT SIGTERM

main "$@"
