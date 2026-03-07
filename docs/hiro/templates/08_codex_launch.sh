#!/bin/bash
# ============================================
# Codex 12 並列エージェント起動スクリプト
# ============================================
# 使い方:
#   bash docs/hiro/templates/08_codex_launch.sh

set -e

TARGET="/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract"
OUTPUT_DIR="outputs/codex_results"

mkdir -p "$OUTPUT_DIR"

echo "=== Codex 12 エージェントを並列起動します ==="
echo "ターゲット: $TARGET"
echo "出力先: $OUTPUT_DIR"
echo ""

BASE_PROMPT="あなたは Sui Move スマートコントラクトセキュリティ監査人です。
ターゲット: $TARGET/contracts/protocol/
contracts/protocol/sources/ と contracts/math/sources/ の全コードを読み、脆弱性を全て見つけてください。
各発見について: タイトル(英語)、深刻度(HIGH/MEDIUM/LOW)、根本原因(ファイル名:行番号+コードスニペット)、攻撃シナリオ、影響、修正案を詳細に報告してください。"

echo "1/12: Flash Loan"
codex exec --skip-git-repo-check -s read-only -q \
  "$BASE_PROMPT 攻撃面: Flash Loan (borrow_flash_loan, repay_flash_loan, hot-potato, 手数料, 再入)" \
  > "$OUTPUT_DIR/01_flash_loan.md" &

echo "2/12: Oracle"
codex exec --skip-git-repo-check -s read-only -q \
  "$BASE_PROMPT 攻撃面: Oracle (get_price, get_spot_price, EMA vs Spot, deviation check, staleness)" \
  > "$OUTPUT_DIR/02_oracle.md" &

echo "3/12: Liquidation"
codex exec --skip-git-repo-check -s read-only -q \
  "$BASE_PROMPT 攻撃面: Liquidation (liquidation_inner, close_factor, seized amount, revenue_factor)" \
  > "$OUTPUT_DIR/03_liquidation.md" &

echo "4/12: eMode"
codex exec --skip-git-repo-check -s read-only -q \
  "$BASE_PROMPT 攻撃面: eMode (borrow cap tracking, collateral_factor, group switching, admin changes)" \
  > "$OUTPUT_DIR/04_emode.md" &

echo "5/12: Interest"
codex exec --skip-git-repo-check -s read-only -q \
  "$BASE_PROMPT 攻撃面: Interest Rate (accrue_interest, simple vs compound, borrow_index, reserve_factor)" \
  > "$OUTPUT_DIR/05_interest.md" &

echo "6/12: Access Control"
codex exec --skip-git-repo-check -s read-only -q \
  "$BASE_PROMPT 攻撃面: Access Control (PackageCallerCap, AdminCap, whitelist, permissions)" \
  > "$OUTPUT_DIR/06_access_control.md" &

echo "7/12: Rate Limiter"
codex exec --skip-git-repo-check -s read-only -q \
  "$BASE_PROMPT 攻撃面: Rate Limiter (add_outflow, reduce_outflow, sliding window, segment管理)" \
  > "$OUTPUT_DIR/07_rate_limiter.md" &

echo "8/12: Deposit/Withdraw"
codex exec --skip-git-repo-check -s read-only -q \
  "$BASE_PROMPT 攻撃面: Deposit/Withdraw (handle_mint, handle_redeem, exchange rate, cToken)" \
  > "$OUTPUT_DIR/08_deposit_withdraw.md" &

echo "9/12: Referral"
codex exec --skip-git-repo-check -s read-only -q \
  "$BASE_PROMPT 攻撃面: Referral (self-referral check, deposit threshold, generate_referral_code)" \
  > "$OUTPUT_DIR/09_referral.md" &

echo "10/12: ADL"
codex exec --skip-git-repo-check -s read-only -q \
  "$BASE_PROMPT 攻撃面: Auto-Deleverage ADL (activation vs stop条件, global vs emode scope)" \
  > "$OUTPUT_DIR/10_adl.md" &

echo "11/12: Math/Precision"
codex exec --skip-git-repo-check -s read-only -q \
  "$BASE_PROMPT 攻撃面: Math/Precision (int_mul floor truncation, ceil, overflow, WAD変換)" \
  > "$OUTPUT_DIR/11_math_precision.md" &

echo "12/12: Reserve/Revenue"
codex exec --skip-git-repo-check -s read-only -q \
  "$BASE_PROMPT 攻撃面: Reserve/Revenue (take_revenue, cash_reserve, protocol fee, repay rounding)" \
  > "$OUTPUT_DIR/12_reserve_revenue.md" &

echo ""
echo "全 12 エージェントをバックグラウンドで起動しました。完了を待機中..."
wait

echo ""
echo "=== 全 Codex エージェント完了 ==="
echo "結果:"
for f in "$OUTPUT_DIR"/*.md; do
  SIZE=$(wc -c < "$f" | tr -d ' ')
  echo "  $(basename $f): ${SIZE} bytes"
done
