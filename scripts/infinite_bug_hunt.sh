#!/bin/bash
# Infinite bug hunting loop for Current Finance audit
# Runs claude code repeatedly, handling rate limits and context resets
#
# Usage:
#   bash scripts/infinite_bug_hunt.sh
#   bash scripts/infinite_bug_hunt.sh --interval 300  # 5min between retries
#
# Features:
# - Auto-restarts after rate limit or context exhaustion
# - Maintains state in data/hunt_state.json
# - Scrapes new data sources each cycle
# - Commits findings automatically

set -euo pipefail

INTERVAL=${1:-180}  # Default: 3 minutes between retries
STATE_FILE="data/hunt_state.json"
LOG_DIR="outputs/logs/hunt"
AUDIT_TARGET="C:\\Users\\shieru_k\\Desktop\\audit-current-main"

mkdir -p "$LOG_DIR" data/c4 data/solodit

# Initialize state if not exists
if [ ! -f "$STATE_FILE" ]; then
    echo '{"cycle": 0, "findings": [], "scraped_c4": false, "scraped_solodit": false, "last_run": ""}' > "$STATE_FILE"
fi

update_state() {
    local key=$1
    local value=$2
    python3 -c "
import json
with open('$STATE_FILE') as f:
    state = json.load(f)
state['$key'] = $value
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f, indent=2)
"
}

get_state() {
    python3 -c "
import json
with open('$STATE_FILE') as f:
    state = json.load(f)
print(state.get('$1', ''))
"
}

log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $1"
    echo "[$timestamp] $1" >> "$LOG_DIR/hunt.log"
}

# Phase 1: Scrape new data if not done
scrape_data() {
    local scraped_c4=$(get_state "scraped_c4")
    if [ "$scraped_c4" != "True" ]; then
        log "Scraping Code4rena HIGHs..."
        python3 scripts/scrape_c4_highs.py --limit 15 2>&1 | tee -a "$LOG_DIR/scrape_c4.log" || true
        update_state "scraped_c4" "True"

        # Commit new data
        git add data/c4/ scripts/scrape_c4_highs.py 2>/dev/null || true
        git commit -m "feat: scrape Code4rena DeFi HIGHs for pattern matching

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>" 2>/dev/null || true
        git push origin hiro/high-bug-hunting 2>/dev/null || true
    fi
}

# Phase 2: Run Claude Code for bug hunting
run_hunt_cycle() {
    local cycle=$(get_state "cycle")
    cycle=$((cycle + 1))
    update_state "cycle" "$cycle"
    update_state "last_run" "\"$(date -Iseconds)\""

    log "=== Hunt Cycle $cycle ==="

    local prompt="Continue HIGH bug hunting for Current Finance (Sherlock #1256) audit.

Context:
- Branch: hiro/high-bug-hunting
- Audit target: $AUDIT_TARGET
- Cycle: $cycle
- Past data: data/sherlock/lending_highs.csv (1,291 HIGHs), data/c4/defi_highs.csv (Code4rena HIGHs)
- Found so far: #062 (bad debt not socialized)
- Already submitted: #003, #009, #031
- Existing HIGH: #048

NEW DATA SOURCES TO ANALYZE:
- data/c4/defi_highs.csv - Code4rena HIGH findings (NEW - not yet analyzed)
- data/c4/*_highs.json - Cached contest data

Strategy for this cycle:
1. If Code4rena data exists, analyze NEW patterns not found in Sherlock data
2. Cross-reference C4 patterns against Current Finance code
3. Focus on Compound V2 fork vulnerabilities in C4 (Venus, Moonwell, etc.)
4. Look for Move/Sui specific bugs (PTB, object ownership, hot potato)
5. When bug found: report -> update issues #138/#140/#142 -> commit with '発見!' -> push

README says: 'SRs should assume bad debt is possible' and 'invariants must hold under flashloan+deposit/borrow in one ptb'

Expert filter: permissionless entry, direct fund loss >1% AND >\$10, no admin preconditions.
Commit and push any new findings."

    # Run claude with the prompt, capture output
    local logfile="$LOG_DIR/cycle_${cycle}_$(date +%Y%m%d_%H%M%S).log"

    log "Running claude code..."
    echo "$prompt" | claude --dangerously-skip-permissions -p 2>&1 | tee "$logfile" || true

    log "Cycle $cycle completed. Exit code: $?"
}

# Main loop
log "Starting infinite bug hunt loop (interval: ${INTERVAL}s)"
log "State file: $STATE_FILE"
log "Press Ctrl+C to stop"

while true; do
    # Phase 1: Scrape data
    scrape_data

    # Phase 2: Run hunt
    run_hunt_cycle

    log "Waiting ${INTERVAL}s before next cycle..."
    sleep "$INTERVAL"
done
