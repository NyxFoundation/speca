#!/bin/bash
# Auto-retry HIGH bug hunting loop
# Scrapes more Sherlock data, rebuilds CSV, and searches for new HIGHs
# Designed to resume automatically after Claude rate limit recovery

set -e
cd "$(dirname "$0")/.."

echo "=== HIGH Bug Hunt Loop $(date) ==="

# Step 1: Continue scraping (50 more contests per run)
echo "[1/3] Scraping Sherlock contests..."
python3 scripts/scrape_all_sherlock.py --limit 50 2>&1 | tail -10 || true

# Step 2: Rebuild CSV
echo "[2/3] Rebuilding CSV..."
python3 scripts/scrape_all_sherlock.py --csv-only 2>&1 | tail -5

# Step 3: Commit new data if any
echo "[3/3] Committing new data..."
cd "$(git rev-parse --show-toplevel)"
NEW_FILES=$(git status --short data/sherlock/ | grep "^??" | wc -l)
if [ "$NEW_FILES" -gt 0 ]; then
    git add data/sherlock/*_highs.json data/sherlock/all_sherlock_highs.csv
    git commit -m "data: add $NEW_FILES more Sherlock contest caches

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>" || true
    git push origin hiro/high-bug-hunting || true
    echo "Committed $NEW_FILES new contest caches"
else
    echo "No new data to commit"
fi

TOTAL=$(ls data/sherlock/*_highs.json 2>/dev/null | wc -l)
echo "=== Done. Total cached contests: $TOTAL ==="
