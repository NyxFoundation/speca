# Sherlock Bug Bounty 量産監査ガイド (人間用)

## この文書は何か

Sherlock Bug Bounty コンテストに対して、AI エージェントを大量並列起動して脆弱性を発見するワークフローの人間向け説明。各ステップで「何をするか」「なぜやるか」「どのテンプレートを使うか」を説明する。

---

## ブランチ戦略

```
main (master)
  SPECA のソースコードのみ。レポートは置かない。
      |
      +-- hiro/<CONTEST_BRANCH> (作業ベースブランチ)
            レポートを溜める場所。各 agent ブランチの PR マージ先。
            |
            +-- <CONTEST_BRANCH>-agent-1  → PR → マージ
            +-- <CONTEST_BRANCH>-agent-2  → PR → マージ
            +-- <CONTEST_BRANCH>-agent-N  → PR → マージ
            |
            (マージ後)
            +-- テンプレート 09 で重複チェック → 統合 or 削除
```

- **main**: コードだけ。監査の成果物は入れない
- **作業ブランチ**: コンテストごとに 1 本。全レポートが集約される場所
- **agent ブランチ**: エージェントが作業して PR → 作業ブランチにマージ → 自動削除
- **重複チェック**: 全 agent マージ後にテンプレート 09 を実行し、重複レポートを統合/削除

---

## 全体フロー

```
Phase 0: 準備 (人間)
  ターゲット情報収集、コードクローン、作業ブランチ作成
      |
Phase 1: 初回並列監査 (AI x N)
  テンプレート 01 を N 個のセッションに投入
  各 agent → PR → 作業ブランチにマージ
      |
Phase 1.5: 重複チェック (AI x 1)
  テンプレート 09 で重複レポート統合/削除
      |
Phase 2: オーケストレーター監査 (AI x 1)
  テンプレート 02 → 内部で 12 並列エージェント → PR → マージ
      |
Phase 3: Codex クロスバリデーション (スクリプト)
  テンプレート 08 のスクリプト直接実行
      |
Phase 4: 深堀りラウンド 2 (AI x 1)
  テンプレート 04 → PR → マージ
      |
Phase 5: クロスバリデーション比較 (AI x 1)
  テンプレート 05 → PR → マージ
      |
Phase 6: 最終洗い出し (AI x 1)
  テンプレート 06 → PR → マージ
      |
Phase 6.5: 最終重複チェック (AI x 1)
  テンプレート 09 で最終整理
```

---

## Phase 0: 準備 (人間が手動で行う)

### 0-1. コンテスト情報を集める

Sherlock のコンテストページから:
- コンテスト番号 (例: #1256)
- プロトコル名 (例: Current Finance)
- ターゲットリポジトリ URL
- コンテスト期間、賞金プール
- スコープ (対象ファイル/コントラクト)
- 言語 (Solidity / Move / Rust / etc.)

### 0-2. ターゲットコードをクローン

```bash
cd /Users/hiro/Documents
git clone <TARGET_REPO_URL>
```

### 0-3. ベースブランチを決める

既存のベースブランチがない場合は新規作成:
```bash
cd /Users/hiro/Documents/security-agent
git checkout -b hiro/<CONTEST_BRANCH> main
git push origin hiro/<CONTEST_BRANCH>
```

### 0-4. テンプレートをカスタマイズ

`docs/hiro/templates/01_single_agent_audit.md` の変数を埋める:
- `{{PROTOCOL_NAME}}` → プロトコル名
- `{{CONTEST_NUMBER}}` → コンテスト番号
- `{{TARGET_PATH}}` → ターゲットコードのパス
- `{{LANGUAGE}}` → プログラミング言語
- `{{BASE_BRANCH}}` → ベースブランチ名
- `{{BRANCH_PREFIX}}` → エージェントブランチの prefix

---

## Phase 1: 量産セッション起動

### 方法 A: happy コマンド (推奨、最も手軽)

ターミナルを N 個開いて、全部同じコマンドを貼るだけ:

```bash
cd /Users/hiro/Documents/security-agent
happy --yolo -p "docs/hiro/templates/01_single_agent_audit.md を読み込み、リモートブランチを確認して空いている最も若い番号を自身のエージェント番号として監査を実行して。既存レポートとの重複は避けること。"
```

### 方法 B: claude コマンド

```bash
cd /Users/hiro/Documents/security-agent
claude -p "docs/hiro/templates/01_single_agent_audit.md を読み込み実行してください。"
```

### 方法 C: スクリプト一括起動

```bash
bash docs/hiro/templates/07_mass_launch.sh 10
```

### 何が起きるか

1. 各セッションが `git branch -r` を確認して空き番号を取得
2. `hiro/<BRANCH_PREFIX>-agent-N` ブランチを作成
3. ターゲットコードを読んで脆弱性を発見
4. `outputs/reports/report_NNN_*.md` にレポートを作成
5. PR を作成して即座にマージ
6. ブランチ削除

---

## Phase 2: オーケストレーター (1 セッションで 12 並列)

テンプレート 02 を使う。1 つの Claude Code セッション内で 12 個の Agent ツール呼び出しを行い、攻撃面ごとに並列分析する。

```bash
claude -p "docs/hiro/templates/02_orchestrator_12_agents.md を読み込み実行してください。"
```

Phase 1 とは別のアプローチ:
- Phase 1: 各セッションが独立に全コードを見る → 同じバグの独立確認が得られる
- Phase 2: 1 セッションが攻撃面を分割して効率的に探索 → 網羅性が高い

---

## Phase 3: Codex クロスバリデーション

Claude とは異なる AI (OpenAI Codex) で同じ分析を行い、発見を比較する。

```bash
# 方法 A: Claude セッション経由
claude -p "docs/hiro/templates/03_codex_12_agents.md を読み込み実行してください。"

# 方法 B: スクリプト直接
bash docs/hiro/templates/08_codex_launch.sh
```

---

## Phase 4-6: 深堀り → 比較 → 最終洗い出し

```bash
# 深堀り (Phase 1-3 の結果を踏まえて)
claude -p "docs/hiro/templates/04_deep_dive_round2.md を読み込み実行してください。"

# 比較 (全結果をまとめる)
claude -p "docs/hiro/templates/05_cross_validation.md を読み込み実行してください。"

# 最終洗い出し (取りこぼしなく全部レポート化)
claude -p "docs/hiro/templates/06_final_sweep.md を読み込み実行してください。"
```

---

## 実績データ (Current Finance / Sherlock #1256)

| Phase | 方法 | 投入数 | 発見数 | 所要時間 |
|-------|------|--------|--------|---------|
| 1 | 12 parallel Claude sessions | 12 | 5 件 (HIGH x1, MEDIUM x4) | ~10分 |
| 2 | 1 orchestrator (12 subagents) | 1 | 3 件追加 (MEDIUM x3) | ~10分 |
| 3 | 12 parallel Codex agents | 12 | 3 新規 + 9 確認 | ~15分 |
| 6 | Final sweep (1 session) | 1 | 14 件追加 | ~20分 |
| **合計** | | | **27 レポート** | **~85分** |

---

## ディレクトリ構成

```
docs/hiro/templates/
  00_human_guide.md            ← この文書 (人間用ガイド)
  01_single_agent_audit.md     ← AI用: 単体監査プロンプト (量産用)
  02_orchestrator_12_agents.md ← AI用: 12 並列オーケストレーター
  03_codex_12_agents.md        ← AI用: Codex 12 並列起動
  04_deep_dive_round2.md       ← AI用: 深堀りラウンド 2
  05_cross_validation.md       ← AI用: クロスバリデーション比較
  06_final_sweep.md            ← AI用: 最終洗い出し
  07_mass_launch.sh            ← スクリプト: N 個のセッション一括起動
  08_codex_launch.sh           ← スクリプト: 12 Codex エージェント起動
  09_dedup_reports.md          ← AI用: マージ後の重複チェック・統合
```

---

## 注意事項

- happy / claude は `cd /Users/hiro/Documents/security-agent` してから起動すること
- Codex は `--skip-git-repo-check` が必要
- Codex は `o3` モデル非対応 (ChatGPT アカウント)。デフォルトモデル使用
- レポートは必ず `outputs/reports/` に配置
- エージェント間の番号衝突は PR マージ時に自然解消 (squash merge)
