# AI エージェント並列監査セッション手順書

## 目的

このドキュメントを新規 Claude Code セッションに食わせるだけで、自動的にブランチ作成 → 監査 → レポート生成 → PR 作成まで完了する。大量のセッションを並列起動して脆弱性発見数を最大化する。

## アーキテクチャ

```
hiro/elegant-wiles (ベースブランチ: 既存レポート + ターゲット情報)
  |
  +-- hiro/elegant-wiles-agent-1  → PR → auto-merge
  +-- hiro/elegant-wiles-agent-2  → PR → auto-merge
  +-- hiro/elegant-wiles-agent-3  → PR → auto-merge
  +-- ...
  +-- hiro/elegant-wiles-agent-N  → PR → auto-merge
```

各エージェントブランチは `outputs/reports/` にレポートを追加し、PR を送ると GitHub Actions が自動マージする。

---

## セッションに渡す指示 (コピペ用)

以下のプロンプトを新規 Claude Code セッションにそのまま貼り付ける。`AGENT_NUMBER` だけ変える。

---

### プロンプト開始

```
あなたは Current Finance (Sherlock #1256) の Sui Move DeFi レンディングプロトコルのセキュリティ監査人です。

## 作業環境セットアップ

1. SPECA リポジトリに移動:
   cd /Users/hiro/Documents/security-agent

2. elegant-wiles ブランチから新規ブランチを作成:
   git fetch origin
   git checkout -b hiro/elegant-wiles-agent-AGENT_NUMBER origin/hiro/elegant-wiles

3. ターゲットコードの場所を確認:
   /Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract/contracts/protocol/

## ターゲット概要

- プロトコル: Current Finance (旧 Pebble) — Sui Move DeFi レンディングプロトコル
- チェーン: Sui (Move 言語)
- 主要コントラクト: contracts/protocol/sources/ 配下
- 主要モジュール:
  - market/market.move — 中核ロジック (deposit, withdraw, borrow, repay, liquidation, flash loan)
  - market/reserve.move — 準備金、金利計算、cToken exchange rate
  - market/obligation.move — ユーザー債務管理
  - market/limiter.move — レート制限 (sliding window)
  - market/interest.move — 金利モデル (kink model)
  - market/adl.move — Auto-Deleverage (自動デレバレッジ)
  - internal/emode.move — Enhanced Mode グループ
  - internal/app.move — PackageCallerCap アクセス制御
  - internal/referral.move — リファラルシステム
  - oracle/user.move — 価格オラクル (Pyth/Switchboard, EMA/Spot)
  - entry_points/ — 外部公開エントリポイント
- 数学ライブラリ: contracts/math/sources/float.move (Decimal型、WAD = 10^18)

## 既存レポート (重複しないこと)

outputs/reports/ に既に以下のレポートがある。これらと重複しない新規発見のみをレポートせよ:

001: ADL Borrow が担保を差し押さえる (HIGH)
002: 静的 close_factor 過剰清算 (HIGH)
003: 清算 Spot vs EMA 価格不一致 (HIGH)
004: ADL borrow グローバル debt チェック (HIGH)
005: eMode borrow tracking desync (MEDIUM)
006: Flash loan referral バイパス (MEDIUM)
007: burn_whitelist に AdminCap なし (MEDIUM)
008: 清算がレートリミッター回避 (MEDIUM)
009: Oracle deviation 非対称 (MEDIUM)
010: Flash loan deposit リミッター操作 (MEDIUM)
011: 清算手数料バイパス (チャンキング) (MEDIUM)
012: 同一秒ゼロ金利借入 (MEDIUM)
013: PackageCallerCap transferable (MEDIUM)
014: take_revenue 金利未反映 (MEDIUM)
015: eMode admin timelock なし (MEDIUM)
016: リミッター token量 USD非対応 (MEDIUM)
017: 利用率 1.0 超過可能 (MEDIUM)
018: Cross-eMode flash loan fee 回避 (MEDIUM)
019: Sybil 自己紹介 (MEDIUM)
020: ゼロミント deposit griefing (MEDIUM)
021: クロスセグメント limiter 不具合 (MEDIUM)
022: Oracle staleness 悪用可能 (MEDIUM)
023: Borrow off-by-one (LOW)
024: 単利 (複利ではない) (LOW)
025: Admin eMode 更新で limiter リセット (MEDIUM)
026: Pyth adapter 起動時 underflow (LOW)
027: Repay 丸め過剰請求 (LOW)

## 作業手順

1. ターゲットコードを徹底的に読む
   - contracts/protocol/sources/ 配下の全 .move ファイル
   - contracts/math/sources/ 配下の全 .move ファイル
   - 特に entry_points/ の公開関数から攻撃面を辿る

2. 以下の観点で脆弱性を探す:
   - STRIDE フレームワーク (Spoofing, Tampering, Repudiation, Information Disclosure, DoS, Elevation of Privilege)
   - CWE Top 25 (CWE-22/78/89/94/200/502/639/770/862)
   - DeFi 固有: 価格操作、フラッシュローン、再入、MEV、オラクル操作、ガバナンス攻撃
   - Move 言語固有: ability 制約、hot-potato パターン、shared object 競合

3. 新規発見ごとに outputs/reports/ に Sherlock 形式でレポートを作成:
   - ファイル名: report_NNN_<snake_case_title>.md (NNN は 028 から連番)
   - 既存レポートの番号 (001-027) は使わないこと

4. レポート形式:

# <タイトル (英語)>

## Summary
<1-2文の要約>

## Vulnerability Detail
<技術的詳細、コードスニペット付き。根本原因のファイル名:行番号を明記>

## Impact
<影響の説明>

## Code Snippet
<ファイル名:行番号のリスト>

## Tool used
Manual Review + Automated Analysis

## Recommendation
<修正案、コードスニペット付き>

5. 全レポート作成後、コミットして PR を送り、即マージする:

   git add outputs/reports/
   git commit -m "feat: agent-AGENT_NUMBER audit findings for Current Finance"
   git push origin hiro/elegant-wiles-agent-AGENT_NUMBER

   gh pr create \
     --base hiro/elegant-wiles \
     --head hiro/elegant-wiles-agent-AGENT_NUMBER \
     --title "Agent AGENT_NUMBER: Current Finance audit findings" \
     --body "Automated audit findings from agent session AGENT_NUMBER"

   # 作成した PR を即座にマージ
   gh pr merge --squash --delete-branch

## 重要な注意

- 既存 27 レポートと重複するものは書かない
- HIGH/MEDIUM 優先。LOW も書いてよいが量より質を重視
- コードスニペットは必ずファイル名と行番号を含める
- 推測ではなく、実際のコードを読んで確認した脆弱性のみ報告
- レポートは outputs/reports/ フォルダに配置 (outputs/ 直下ではない)
```

### プロンプト終了

---

## セッション起動手順

### 1. 手動起動の場合

```bash
# ターミナルを N 個開いて、それぞれに:
cd /Users/hiro/Documents/security-agent
claude

# 上記プロンプトを貼り付け (AGENT_NUMBER を 1, 2, 3, ... に変更)
```

### 2. スクリプト一括起動の場合

```bash
#!/bin/bash
# launch_agents.sh — N 個の Claude Code セッションを並列起動

SPECA_DIR="/Users/hiro/Documents/security-agent"
PROMPT_FILE="docs/hiro/sinkisesshon.md"
NUM_AGENTS=${1:-5}

for i in $(seq 1 $NUM_AGENTS); do
  AGENT_PROMPT=$(cat <<PROMPT
上記の docs/hiro/sinkisesshon.md のプロンプトを実行してください。
AGENT_NUMBER=$i です。
PROMPT
  )

  # 新しいターミナルタブで起動 (macOS)
  osascript -e "
    tell application \"Terminal\"
      do script \"cd $SPECA_DIR && claude --print '$AGENT_PROMPT'\"
    end tell
  " &
done

echo "$NUM_AGENTS 個のエージェントセッションを起動しました"
```

### 3. Codex 並列起動の場合

```bash
#!/bin/bash
# launch_codex_agents.sh

TARGET="/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract"
OUTPUT_DIR="outputs/codex_results"
mkdir -p $OUTPUT_DIR

SURFACES=(
  "flash_loan"
  "oracle_price"
  "liquidation"
  "emode_groups"
  "interest_rate"
  "access_control"
  "rate_limiter"
  "deposit_withdraw"
  "referral_system"
  "auto_deleverage"
  "math_precision"
  "reserve_revenue"
)

for surface in "${SURFACES[@]}"; do
  codex exec \
    --skip-git-repo-check \
    -s read-only \
    -q \
    "あなたは Sui Move スマートコントラクトセキュリティ監査人です。
    ターゲット: $TARGET
    攻撃面: $(echo $surface | tr '_' ' ')

    contracts/protocol/sources/ と contracts/math/sources/ の全コードを読み、
    この攻撃面に関連する脆弱性を全て見つけてください。

    各発見について:
    - タイトル (英語)
    - 深刻度 (HIGH/MEDIUM/LOW)
    - 根本原因 (ファイル名:行番号 + コードスニペット)
    - 攻撃シナリオ
    - 影響
    - 修正案
    を詳細に報告してください。" \
    > ${OUTPUT_DIR}/${surface}.md &
done

wait
echo "全 Codex エージェント完了"
```

---

## PR マージ方式

各エージェントが自身の PR を作成し、`gh pr merge --squash --delete-branch` で即座にマージする。
GitHub Actions は不要。エージェント側で完結する。

コンフリクトが発生した場合:
```bash
git fetch origin hiro/elegant-wiles
git rebase origin/hiro/elegant-wiles
git push --force-with-lease origin hiro/elegant-wiles-agent-AGENT_NUMBER
gh pr merge --squash --delete-branch
```

---

## ベストプラクティス

1. **エージェント数**: 5-12 個が最適。それ以上は重複発見が増える
2. **多様性**: 各エージェントに異なる攻撃面フォーカスを与えると効率的
3. **クロスバリデーション**: 2つ以上のエージェントが独立発見した脆弱性は信頼度が高い
4. **Codex 併用**: Claude と Codex で異なるモデルの視点を得る
5. **レポート番号**: 028 から開始、重複しないよう注意。エージェント間で番号が被る可能性あるが PR マージ時に解決

---

## 前回実績 (Current Finance / Sherlock #1256)

| 方法 | エージェント数 | 発見数 | 所要時間 |
|------|-------------|--------|---------|
| SPECA Pipeline | 1 | 2 (HIGH) | ~30分 |
| Claude Round 1 | 12 | 5 (HIGH x1, MEDIUM x4) | ~10分 |
| Claude Round 2 | 12 | 3 (MEDIUM x3) | ~10分 |
| Codex | 12 | 3 新規 + 9 確認 | ~15分 |
| 最終洗い出し | 1 | 14 追加 | ~20分 |
| **合計** | — | **27 レポート** | **~85分** |
