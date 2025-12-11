#!/bin/bash
set -e

# Configuration (match preparation.yml)
export TARGET_REPO="ethereum/go-ethereum"
export TARGET_REF="master"
export TARGET_DIRECTORY="."
export CATEGORY="ethereum-el"
export PROJECT_NAME="Geth (go-ethereum)"
export REFERENCE_URLS="https://ethereum.github.io/execution-specs/src/,https://geth.ethereum.org/docs"

# Permissions to allow non-interactive file writes
export CLAUDE_CODE_PERMISSIONS="bypassPermissions"

# Working directory
WORKDIR="target_workspace"

echo "Using target workspace: $WORKDIR"

if [ ! -d "$WORKDIR" ]; then
    echo "Error: $WORKDIR does not exist. Please checkout the target repo first."
    echo "Try: git clone https://github.com/$TARGET_REPO $WORKDIR"
    exit 1
fi

# Ensure local root outputs directory exists
mkdir -p outputs

# Ensure target workspace outputs directory exists (no symlink)
# We let claude write here, then move files later to avoid sandbox issues with symlinks
if [ -L "$WORKDIR/outputs" ]; then
    rm "$WORKDIR/outputs"
fi
mkdir -p "$WORKDIR/outputs"

# Ensure logs directory exists
mkdir -p outputs/logs

# Function to run claude
run_step() {
    PROMPT_FILE=$1
    EXPECTED_OUTPUT=$2
    LOG_FILE="outputs/logs/${PROMPT_FILE%.md}.json"
    echo "⭐ Running $PROMPT_FILE..."
    
    cd "$WORKDIR"
    
    # Read prompt content
    PROMPT_CONTENT=$(cat "../prompts/$PROMPT_FILE")
    
    # Execute claude with permission bypass and specified agent 'serena'
    # Output format set to json for parsing usage
    START_TIME=$(date +%s)
    if [ "$PROMPT_FILE" == "01_spec.md" ]; then
        claude --dangerously-skip-permissions --agent serena --output-format json -p "$PROMPT_CONTENT TARGET_DIRECTORY=$TARGET_DIRECTORY CATEGORY=$CATEGORY PROJECT_NAME=\"$PROJECT_NAME\" REFERENCE_URLS=\"$REFERENCE_URLS\"" > "../$LOG_FILE"
    else
        claude --dangerously-skip-permissions --agent serena --output-format json -p "$PROMPT_CONTENT" > "../$LOG_FILE"
    fi
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    
    # Check output
    if [ ! -f "outputs/$EXPECTED_OUTPUT" ]; then
        echo "❌ Error: Expected output outputs/$EXPECTED_OUTPUT was not created."
        # Print error details from json if available
        grep "error" "../$LOG_FILE" || true
        exit 1
    fi

    # Extract usage stats for verification
    INPUT_TOKENS=$(grep -o '"input_tokens":[0-9]*' "../$LOG_FILE" | head -1 | cut -d: -f2)
    OUTPUT_TOKENS=$(grep -o '"output_tokens":[0-9]*' "../$LOG_FILE" | head -1 | cut -d: -f2)
    COST=$(grep -o '"total_cost_usd":[0-9.]*' "../$LOG_FILE" | head -1 | cut -d: -f2)

    cd ..
    echo "✅ Finished $PROMPT_FILE (Time: ${DURATION}s | Tokens: In=$INPUT_TOKENS, Out=$OUTPUT_TOKENS | Cost: \$$COST)"
}

# Run steps
run_step "01_spec.md" "01_SPEC.json"
run_step "01b_trustmodel.md" "01b_TRUSTMODEL.json"
run_step "01c_prop.md" "01c_PROP.json"
run_step "02_checklist.md" "02_CHECKLIST.json"

# Copy outputs back to root
echo "📦 Moving outputs to ./outputs/"
cp -r "$WORKDIR/outputs/"* outputs/ 2>/dev/null || true

echo "🎉 All local steps completed! check ./outputs/"
echo "📊 Execution Logs available at ./outputs/logs/"
