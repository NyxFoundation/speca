#!/bin/bash
# ============================================
# 大量 AI エージェント並列起動スクリプト
# ============================================
# 使い方:
#   bash docs/hiro/templates/07_mass_launch.sh          # デフォルト 5 個
#   bash docs/hiro/templates/07_mass_launch.sh 10        # 10 個
#   bash docs/hiro/templates/07_mass_launch.sh 10 happy  # happy で 10 個
#   bash docs/hiro/templates/07_mass_launch.sh 5 claude  # claude で 5 個

set -e

SPECA_DIR="/Users/hiro/Documents/security-agent"
NUM_AGENTS=${1:-5}
CLI_CMD=${2:-happy}  # happy or claude

PROMPT='docs/hiro/templates/01_single_agent_audit.md を読み込み、リモートブランチを確認して空いている最も若い番号を自身のエージェント番号として監査を実行して。既存レポートとの重複は避けること。'

echo "=== $NUM_AGENTS 個の $CLI_CMD セッションを起動します ==="
echo "ディレクトリ: $SPECA_DIR"
echo ""

for i in $(seq 1 $NUM_AGENTS); do
  echo "--- Agent $i を起動中 ---"

  if [ "$CLI_CMD" = "happy" ]; then
    osascript -e "
      tell application \"Terminal\"
        do script \"cd $SPECA_DIR && happy --yolo -p \\\"$PROMPT\\\"\"
      end tell
    " &
  else
    osascript -e "
      tell application \"Terminal\"
        do script \"cd $SPECA_DIR && claude -p \\\"$PROMPT\\\"\"
      end tell
    " &
  fi

  # 番号衝突防止のため少しずらす
  sleep 3
done

echo ""
echo "=== $NUM_AGENTS 個のエージェントを起動しました ==="
echo "各ターミナルタブで実行中。完了すると自動で PR がマージされます。"
