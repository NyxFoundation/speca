#!/bin/bash
set -e

# Configuration
export TARGET_DIRECTORY="."
export WORKDIR="."  # We run from root for this script context
export LOG_DIR="outputs/logs"

# Ensure output directories exist
mkdir -p outputs
mkdir -p "$LOG_DIR"

# Check prerequisites
if [ ! -f "outputs/02_CHECKLIST.json" ]; then
    echo "❌ Error: outputs/02_CHECKLIST.json not found."
    echo "   Please run ./run_local.sh (Preparation Phase) first."
    exit 1
fi

# Function to run claude
run_step() {
    PROMPT_FILE=$1
    EXPECTED_OUTPUT=$2
    ARGS=$3 # Optional arguments for the prompt
    
    LOG_FILE="$LOG_DIR/${PROMPT_FILE%.md}.json"
    echo "⭐ Running $PROMPT_FILE..."
    
    # Read prompt content
    PROMPT_CONTENT=$(cat "prompts/$PROMPT_FILE")
    
    START_TIME=$(date +%s)
    
    # Execute claude with optimizations:
    # 1. --dangerously-skip-permissions: Bypass sandbox prompts
    # 2. --agent serena: Use cost-optimized agent
    # 3. --output-format json: Capture metrics
    if [ -n "$ARGS" ]; then
        # Append args to prompt content if provided
        claude --dangerously-skip-permissions --agent serena --output-format json -p "$PROMPT_CONTENT $ARGS" > "$LOG_FILE"
    else
        claude --dangerously-skip-permissions --agent serena --output-format json -p "$PROMPT_CONTENT" > "$LOG_FILE"
    fi
    
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    
    # Check output existence
    if [ ! -f "outputs/$EXPECTED_OUTPUT" ]; then
        echo "❌ Error: Expected output outputs/$EXPECTED_OUTPUT was not created."
        grep "error" "$LOG_FILE" || true
        exit 1
    fi

    # Extract usage stats
    INPUT_TOKENS=$(grep -o '"input_tokens":[0-9]*' "$LOG_FILE" | head -1 | cut -d: -f2)
    OUTPUT_TOKENS=$(grep -o '"output_tokens":[0-9]*' "$LOG_FILE" | head -1 | cut -d: -f2)
    COST=$(grep -o '"total_cost_usd":[0-9.]*' "$LOG_FILE" | head -1 | cut -d: -f2)

    echo "✅ Finished $PROMPT_FILE (Time: ${DURATION}s | Tokens: In=$INPUT_TOKENS, Out=$OUTPUT_TOKENS | Cost: \$$COST)"
}

# --- Audit Execution ---

# Step 03: Static Audit Map
# Scans the target directory based on the checklist.
# Defaulting PATH to "." (current directory) as per typical usage.
run_step "03_auditmap.md" "03_AUDITMAP.json" "PATH=$TARGET_DIRECTORY"

# Step 04: Review
# reviews the audit map findings and standardizes them.
run_step "04_review.md" "03_AUDITMAP.json"

echo "🎉 All audit steps completed! check outputs/03_AUDITMAP.json"
echo "📊 Execution Logs available at $LOG_DIR"
