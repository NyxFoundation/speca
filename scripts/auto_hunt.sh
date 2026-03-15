#!/bin/bash
# auto_hunt.sh — Watchdog that auto-restarts Claude Code on rate limit recovery
#
# Usage:
#   bash scripts/auto_hunt.sh
#   bash scripts/auto_hunt.sh --interval 300  # check every 5 min (default: 10 min)
#
# What it does:
#   1. Runs Claude Code with the HIGH bug hunting prompt
#   2. If Claude exits (rate limit or otherwise), waits and retries
#   3. On each retry, first runs the scraper (no Claude needed)
#   4. Then relaunches Claude for code analysis
#   5. Loops indefinitely until manually stopped (Ctrl+C)

set -euo pipefail
cd "$(dirname "$0")/.."

INTERVAL="${1:-600}"  # Default 10 minutes between retries
MAX_RETRIES=100
RETRY_COUNT=0
LOG_DIR="outputs/logs"
mkdir -p "$LOG_DIR"

# The prompt to send to Claude Code on each session
HUNT_PROMPT='Continue HIGH bug hunting for Current Finance audit.

Target: C:\Users\shieru_k\Desktop\audit-current-main\sui-move-contract
Issue: https://github.com/NyxFoundation/security-agent/issues/138
Template: docs/report_templates/sherlock.md
Branch: hiro/high-bug-hunting

Tasks:
1. Run scraper: python3 scripts/scrape_all_sherlock.py --limit 50
2. Rebuild CSV: python3 scripts/scrape_all_sherlock.py --csv-only
3. Analyze NEW patterns from expanded dataset against Current Finance code
4. If new HIGH found: generate report (Sherlock template), create PoC, update issue #138, commit & push
5. Focus on patterns with >10 Sherlock occurrences not yet checked
6. Commit new scraper data: git add data/sherlock/ && git commit && git push

Already found HIGHs: #003 (spot/EMA), #048 (close factor bypass), #062 (bad debt not socialized)
Already checked patterns: shares/assets confusion, exchange rate manipulation, first depositor, treasury fee, interest accrual ordering, flash loan reentrancy, oracle manipulation, precision/rounding

Keep going until all 290 contests scraped and all patterns exhausted.'

echo "=========================================="
echo " AUTO HIGH BUG HUNT - Watchdog Mode"
echo " Interval: ${INTERVAL}s between retries"
echo " Target: Current Finance (Sui Move)"
echo " Log dir: $LOG_DIR"
echo "=========================================="

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOG_FILE="$LOG_DIR/auto_hunt_${TIMESTAMP}.log"

    echo ""
    echo "[$(date)] === Attempt $RETRY_COUNT / $MAX_RETRIES ==="

    # Step 1: Run scraper independently (no Claude needed, no rate limit)
    echo "[$(date)] Running Sherlock scraper..."
    python3 scripts/scrape_all_sherlock.py --limit 30 2>&1 | tail -5 || true
    python3 scripts/scrape_all_sherlock.py --csv-only 2>&1 | tail -3 || true

    # Step 2: Commit scraper results
    if git status --short data/sherlock/ | grep -q "^??"; then
        echo "[$(date)] Committing new scraper data..."
        git add data/sherlock/*_highs.json data/sherlock/all_sherlock_highs.csv 2>/dev/null || true
        git commit -m "data: auto-hunt scraper batch $RETRY_COUNT

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>" 2>/dev/null || true
        git push origin hiro/high-bug-hunting 2>/dev/null || true
    fi

    # Step 3: Launch Claude Code for analysis
    echo "[$(date)] Launching Claude Code session..."
    claude --print "$HUNT_PROMPT" 2>&1 | tee "$LOG_FILE" || true

    EXIT_CODE=$?
    echo "[$(date)] Claude exited with code $EXIT_CODE"

    # Check if we hit rate limit
    if grep -qi "rate.limit\|429\|too many\|overloaded" "$LOG_FILE" 2>/dev/null; then
        echo "[$(date)] Rate limit detected. Waiting ${INTERVAL}s before retry..."
        sleep "$INTERVAL"
    elif grep -qi "error\|failed" "$LOG_FILE" 2>/dev/null; then
        echo "[$(date)] Error detected. Waiting ${INTERVAL}s..."
        sleep "$INTERVAL"
    else
        echo "[$(date)] Session completed normally."
        # Still wait a bit to avoid hammering
        sleep 60
    fi
done

echo "[$(date)] Max retries ($MAX_RETRIES) reached. Exiting."
