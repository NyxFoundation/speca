# 新規セッション用 — Sherlock Bug Bounty 監査手順書

## 概要

この文書は、Sherlock Bug Bounty コンテストに対して SPECA パイプライン + 並列エージェント分析 + Codex クロスバリデーションを実行するための手順書です。新しいセッションでそのまま実行できます。

## 前提条件

- Claude Code CLI がインストール済み
- Codex CLI がインストール済み (`npm i -g @openai/codex`)
- `uv` がインストール済み
- SPECA リポジトリ: `/Users/hiro/Documents/security-agent`
- Tree-sitter MCP サーバーが設定済み

## ステップ 1: ターゲット情報収集

```
Sherlock のコンテストページから以下を取得:
- コンテスト番号 (例: #1256)
- プロトコル名 (例: Current Finance / Pebble)
- ターゲットリポジトリ URL
- コンテスト期間
- 賞金プール
- スコープ (対象コントラクト)
```

## ステップ 2: ターゲットコードのクローン

```bash
# ターゲットリポジトリをクローン
cd /Users/hiro/Documents
git clone <TARGET_REPO_URL>
cd <TARGET_DIR>

# コントラクトの構造を確認
find . -name "*.move" -o -name "*.sol" -o -name "*.rs" | head -50
```

## ステップ 3: ワークツリー作成

SPECA リポジトリでワークツリーを作成し、ブランチを切る。

```bash
cd /Users/hiro/Documents/security-agent
git worktree add .claude/worktrees/<BRANCH_NAME> -b hiro/<BRANCH_NAME>
cd .claude/worktrees/<BRANCH_NAME>
```

## ステップ 4: 攻撃面の特定

ターゲットのコードを読み、以下の攻撃面リストを作成する:

### DeFi レンディングプロトコルの場合の典型的な攻撃面:
1. Flash Loan — 再入、手数料、ホットポテト
2. Oracle — 価格操作、EMA vs Spot、staleness
3. Liquidation — 清算ロジック、インセンティブ、閾値
4. eMode — グループ間の不整合、パラメータ
5. Interest — 金利計算、複利、accrual タイミング
6. Access Control — 権限管理、CapabilityパターンRate Limiter — レート制限、バイパス
8. Deposit/Withdraw — exchange rate、ゼロミント
9. Referral — Sybil、閾値バイパス
10. ADL (Auto-Deleverage) — 発動条件、停止条件
11. Math/Precision — 丸め誤差、オーバーフロー
12. Reserve/Revenue — 収益管理、準備金

### スマートコントラクト一般の場合:
1. 再入攻撃
2. アクセス制御
3. 整数オーバーフロー/アンダーフロー
4. 価格操作
5. フラッシュローン攻撃
6. フロントランニング/MEV
7. ストレージ衝突
8. 初期化問題
9. 委任呼び出し
10. ガスグリーフィング

## ステップ 5: 並列 Claude エージェント起動 (ラウンド 1)

12個の並列エージェントを起動する。各エージェントに1つの攻撃面を割り当て。

```
以下の形式で Agent ツールを使い、12個を同時起動:

Agent(
  description="Audit <ATTACK_SURFACE>",
  prompt="""
  あなたはスマートコントラクトセキュリティ監査人です。

  ターゲット: <TARGET_PATH>
  攻撃面: <ATTACK_SURFACE>

  以下の手順で分析してください:

  1. 対象コードの全ファイルを読む
  2. <ATTACK_SURFACE> に関連する脆弱性を探す
  3. STRIDE フレームワーク + CWE Top 25 を適用
  4. 各発見について:
     - 脆弱性タイトル
     - 深刻度 (HIGH/MEDIUM/LOW)
     - 根本原因 (ファイル名:行番号 + コードスニペット)
     - 攻撃シナリオ
     - 影響
     - 修正案

  結果を JSON 形式で出力:
  {
    "attack_surface": "<ATTACK_SURFACE>",
    "findings": [
      {
        "title": "...",
        "severity": "HIGH|MEDIUM|LOW",
        "root_cause": "file.move:123",
        "description": "...",
        "impact": "...",
        "recommendation": "..."
      }
    ]
  }
  """,
  subagent_type="general-purpose"
)
```

## ステップ 6: ラウンド 1 結果の整理

1. 全エージェントの結果を収集
2. 重複排除 — 複数エージェントが同じ脆弱性を発見した場合は独立確認としてカウント
3. HIGH/MEDIUM の発見に対して Sherlock 形式のレポートを作成

### Sherlock レポート形式:

```markdown
# <タイトル>

## Summary
<1-2文の要約>

## Vulnerability Detail
<技術的詳細、コードスニペット付き>

## Impact
<影響の説明>

## Code Snippet
<ファイル名:行番号のリンク>

## Tool used
Manual Review + Automated Analysis

## Recommendation
<修正案、コードスニペット付き>
```

## ステップ 7: ラウンド 2 深堀り分析

ラウンド 1 で発見された攻撃面のうち、特に複雑なものを再度12個の並列エージェントで深堀り。各エージェントには:
- ラウンド 1 の発見内容を渡す
- 「これ以外に見落としがないか」を明示的に指示
- より具体的なコードパスを指定

## ステップ 8: Codex クロスバリデーション

同じ12の攻撃面を Codex CLI で並列実行:

```bash
# 12個の Codex エージェントを並列起動
for i in 01_flash_loan 02_oracle 03_liquidation 04_emode 05_interest 06_access_control 07_rate_limiter 08_deposit_withdraw 09_referral 10_adl 11_math_precision 12_reserve_revenue; do
  codex exec \
    --skip-git-repo-check \
    -s read-only \
    -q \
    "あなたはスマートコントラクトセキュリティ監査人です。
    ターゲット: <TARGET_PATH>
    攻撃面: $(echo $i | sed 's/[0-9]*_//; s/_/ /g')

    この攻撃面に関連する全てのコードファイルを読み、
    脆弱性を見つけてください。

    各発見について:
    - タイトル
    - 深刻度 (HIGH/MEDIUM/LOW)
    - 根本原因 (ファイル名:行番号)
    - 攻撃シナリオ
    - 修正案
    を報告してください。" \
    > outputs/codex_results/${i}.md &
done
wait
```

## ステップ 9: クロスバリデーション比較

1. Claude の発見と Codex の発見を比較
2. 両方が確認した発見 → 信頼度 HIGH
3. 片方のみの発見 → ソースコードで手動検証
4. Codex のみの新規発見 → 追加レポート作成

## ステップ 10: コミットとプッシュ

```bash
cd /Users/hiro/Documents/security-agent/.claude/worktrees/<BRANCH_NAME>
git add outputs/
git commit -m "feat: <PROTOCOL_NAME> (Sherlock #XXXX) full audit results"
git push origin hiro/<BRANCH_NAME>
```

---

## 前回の実行例 (Current Finance / Sherlock #1256)

### ターゲット
- プロトコル: Current Finance (旧 Pebble)
- チェーン: Sui (Move 言語)
- 種別: DeFi レンディングプロトコル
- リポジトリ: `/Users/hiro/Documents/2026-03-currentsui-contest-march-2026-grandchildrice-main/sui-move-contract`
- ブランチ: `hiro/elegant-wiles`

### 成果物
- 合計 27 レポート (report_001 〜 report_027)
- HIGH: 4件 (001-004)
- MEDIUM: 17件 (005-025 の大部分)
- LOW: 6件 (023, 024, 026, 027 等)

### 確認方法
- Claude ラウンド 1: 12並列エージェント → 7件発見
- Claude ラウンド 2: 12並列エージェント → 3件追加
- Codex 12並列エージェント → 3件新規 + 既存9件確認
- 最終洗い出し → 14件追加

### タイムライン
1. SPECA パイプラインで初期2件 (001, 002)
2. Claude ラウンド 1 → 003-007
3. Claude ラウンド 2 → 008-010
4. Codex クロスバリデーション → 011-013
5. 全ファインディング洗い出し → 014-027

---

## 注意事項

- Codex は `o3` モデル非対応 (ChatGPT アカウント使用時)。デフォルトモデルを使用
- `--skip-git-repo-check` フラグが必要 (ターゲットディレクトリが信頼済みでない場合)
- Codex は `-s read-only` で読み取り専用サンドボックスを使用
- レポートファイル名: `outputs/report_XXX_<snake_case_title>.md`
- Codex 結果: `outputs/codex_results/<NN>_<attack_surface>.md`
