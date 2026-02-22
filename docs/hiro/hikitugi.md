# 引き継ぎ資料 — SPECA セキュリティエージェント

> 次回セッション開始時にこのファイルを読んで状況を把握してください。
> 最終更新: 2026-02-22

---

## 1. プロジェクト概要

**SPECA** (Specification-to-Checklist Agentic Auditing) は、Claude Code CLI を使った自動セキュリティ監査パイプラインです。仕様書からプログラムグラフを構築し、セキュリティプロパティを生成、監査チェックリストを作成し、ターゲットコードに対して3フェーズの形式的監査を行います。

詳細は `CLAUDE.md`（リポジトリルート）を参照。

---

## 2. リポジトリ構成

```
security-agent/
├── CLAUDE.md                          # Claude Code 用プロジェクト規約（必読）
├── pyproject.toml                     # Python 依存関係（uv, Python >=3.11）
├── .claude/skills/                    # スキル定義（SKILL.md）
├── scripts/
│   ├── run_phase.py                   # パイプライン実行エントリポイント
│   ├── setup_mcp.sh                   # MCP サーバー登録スクリプト
│   └── orchestrator/                  # 非同期 Python オーケストレーター
│       ├── base.py                    # BaseOrchestrator（並列実行、レジューム）
│       ├── config.py                  # PhaseConfig（全フェーズ定義）
│       ├── runner.py                  # ClaudeRunner（CLI 呼び出し、サーキットブレーカー）
│       ├── watchdog.py                # LogWatcher、CostTracker（予算管理）
│       ├── resume.py                  # ResumeManager（部分結果からのレジューム）
│       ├── collector.py               # ResultCollector（部分結果の即時保存）
│       ├── schemas.py                 # Pydantic データ契約（フェーズ間検証）
│       ├── batch.py                   # バッチ戦略
│       ├── queue.py                   # キュー管理
│       └── factory.py                 # オーケストレーター生成
├── prompts/                           # フェーズ別ワーカープロンプト
├── outputs/                           # パイプライン出力（PARTIAL_*.json）
├── tests/                             # pytest テスト（178件）
│   ├── test_schemas_and_config.py     # メインテスト（スキーマ、設定、回路遮断器）
│   ├── test_code_scope.py
│   ├── test_phase03_early_exit.py
│   ├── test_watchdog_cache_tokens.py
│   └── verify_phase02_fix.py
├── benchmarks/                        # ベンチマーク（RQ1: 脆弱性DB精度, RQ2: ツール比較）
│   ├── rq1/                           # RQ1 評価パイプライン
│   ├── rq2/                           # RQ2 評価パイプライン
│   │   ├── evaluate.py                # ★修正済み（bootstrap_metric_diffs 引数追加）
│   │   └── generate_report.py
│   ├── runners/                       # ツール実行ラッパー
│   │   ├── run_semgrep.py
│   │   ├── run_codeql.py
│   │   ├── run_llm_baseline.py
│   │   ├── run_static_baseline.py
│   │   ├── run_security_agent.py
│   │   └── invoke_security_agent.sh   # ★新規（プレースホルダー）
│   ├── scripts/
│   │   └── run_rq2_local.sh           # ★新規（ローカル一括実行）
│   ├── datasets/                      # データセットビルダー
│   │   └── builders/setup_benchmark.py # ★修正済み（ROOT_DIR, HF ミラー）
│   ├── metrics/                       # 統計ユーティリティ
│   │   ├── classification.py
│   │   └── stats.py
│   └── tools/                         # ツールレジストリ・ローダー
├── .github/workflows/                 # CI/CD
│   ├── 01a-discovery.yml ... 04-audit-review.yml  # パイプラインフェーズ
│   ├── benchmark-rq2-01-setup.yml     # RQ2 ステップ1: データセットセットアップ
│   ├── benchmark-rq2-02-tools.yml     # ★修正済み（security_agent 統合）
│   └── benchmark-rq2-03-evaluate.yml  # ★修正済み（レポート生成・artifact）
└── docs/
    ├── hikitugi.md                    # ← この文書
    ├── LOCAL_VERIFICATION_GUIDE.md    # ローカル実行ガイド（日本語）
    ├── CLAUDE_CACHE_STRATEGY.md
    ├── ethereum/                      # Ethereum 仕様・バグデータ
    └── report_templates/              # バグバウンティレポートテンプレート
```

---

## 3. 現在のブランチ状態

| 項目 | 値 |
|------|-----|
| **作業ブランチ** | `claude/understand-project-overview-RPCCv` |
| **ベースブランチ** | `master` |
| **master からの差分** | 15 コミット, 30 ファイル変更, +7246 行 |
| **テスト** | 178 passed (全パス) |

### ブランチ上のコミット履歴（古い順）

| # | コミット | 内容 |
|---|---------|------|
| 1 | `f455a47` | `setup_benchmark.py` 修正: ROOT_DIR パス修正、公開 HF ミラー使用、ダウンロード検証追加 |
| 2 | `7154a45` | `docs/LOCAL_VERIFICATION_GUIDE.md` 新規: ローカル手動確認ガイド（日本語） |
| 3 | `7560c86` | RQ2 ワークフロー間のデータセットアーティファクトキャッシング追加 |
| 4 | `1ea6c7c` | LOCAL_VERIFICATION_GUIDE にデータセットキャッシュ検証セクション追加 |
| 5 | `65e13df` | **RQ2 パイプライン改善（メイン作業）**: evaluate.py 修正、ワークフロー改善、スクリプト新規作成 |
| 6 | `6332f09` | 引き継ぎ資料 `docs/hikitugi.md` 追加 |
| 7 | `a3ba5b4` | RQ2 ワークフローから git push を削除、artifact のみに統一 |
| 8 | `cacd5a7` | PR #55 マージ（ベンチマーク実装検証） |
| 9 | `72f34b3` | Dockerfile PYTHONPATH 修正、`--tmp-dir` 不足修正、`continue-on-error` 追加 |
| 10 | `7c9e17c` | データセット fetch スクリプトにデバッグ出力と広範ファイル検索追加 |
| 11 | `ed95762` | 評価パイプラインの ID ミスマッチ修正 + Semgrep 結果 & 可視化追加 |
| 12 | `f48fc85` | LLM ベースライン結果追加（全エラー、CI 再実行が必要） |
| 13 | `9bfc9b5` | Docker import 用 `__init__.py` 追加 + 評価結果更新 |
| 14 | `6d03e79` | Docker root 所有ファイルのパーミッションエラー修正（初回: `sudo find -not -writable`） |
| 15 | `49bbed8` | **パーミッション修正 v2**: `sudo find -not -writable` → `sudo chown -R` に変更 |

---

## 4. セッション別の変更履歴

### セッション 1 (2026-02-21): RQ2 パイプライン構築

#### 4.1 `benchmarks/rq2/evaluate.py` — バグ修正

**問題**: `stats.py:54` の `bootstrap_metric_diffs()` は `samples`, `seed`, `ci_level` を必須引数として要求するが、`evaluate.py:344` では渡していなかった。security_agent の結果がある状態で `evaluate.py` を実行すると `TypeError` で即座にクラッシュする。

**修正**: 344行目の呼び出しにキーワード引数3つを追加。

```python
# evaluate.py:344-352 （修正後）
diffs = bootstrap_metric_diffs(
    predictions_by_tool["security_agent"],
    predictions_by_tool[tool],
    ground_truth,
    eligible_cases,
    samples=BOOTSTRAP_SAMPLES,   # ← 追加
    seed=BOOTSTRAP_SEED,         # ← 追加
    ci_level=CI_LEVEL,           # ← 追加
)
```

#### 4.2 `.github/workflows/benchmark-rq2-02-tools.yml` — security_agent 統合

主な変更:
- `security_agent_command` 入力パラメータ追加（外部から `--command` テンプレートを渡せるように）
- ツール選択の `run_security_agent=false` 固定 → `true` に修正（`all` 選択時に含まれるように）
- 「Run Security Agent」ステップ実装（`--command` 未指定時はプレースホルダー JSON で正常終了）
- `upload-artifact` + `~/.cache` 保存ステップ追加
- git push は残存（下流ワークフローが `ref:` で checkout するため必要）

#### 4.3 `.github/workflows/benchmark-rq2-03-evaluate.yml` — 評価パイプライン完成

主な変更:
- `tools_run_id`, `rq1_summary` 入力パラメータ追加
- tool results の artifact download + `~/.cache` fallback 追加
- `generate_report.py` 実行ステップ追加
- `upload-artifact` + `~/.cache` 保存ステップ追加
- `$GITHUB_STEP_SUMMARY` にレポート全文出力

#### 4.4 `benchmarks/runners/invoke_security_agent.sh` — 新規

security-agent 単一ファイル監査のプレースホルダースクリプト。`{code_path}`, `{output_path}`, `{case_id}` を受け取り、予測 JSON を出力する形式。**本体は未実装**で `"error": "not_implemented"` を返す。

#### 4.5 `benchmarks/scripts/run_rq2_local.sh` — 新規

ローカル一括実行スクリプト。Step 1（データセット）→ Step 2（ツール実行）→ Step 3（評価）→ Step 4（レポート生成）→ Step 5（キャッシュ）を順次実行。既存結果がある場合はスキップ。

```bash
# 使い方
bash benchmarks/scripts/run_rq2_local.sh                        # PrimeVul, Semgrep のみ
bash benchmarks/scripts/run_rq2_local.sh primevul all 100       # 全ツール, 100サンプル
bash benchmarks/scripts/run_rq2_local.sh primevul semgrep,codeql
```

### セッション 2 (2026-02-22): CI パーミッションエラー修正

#### 4.6 Docker root 所有ファイルのパーミッションエラー修正

**問題**: self-hosted ランナーで `actions/checkout@v4` が `__pycache__/*.pyc` ファイルを削除できず失敗。Docker がコンテナ内で root として作成したファイルがワークスペースに残り、ランナーユーザー（`gohan`）が unlink できない。

**初回修正 (`6d03e79`)**: `sudo find -not -writable -delete` をチェックアウト前に実行。

**問題の再発 (`49bbed8`)**: `sudo find -not -writable` は `sudo` で実行されるため `find` プロセスが root として動作し、root にとっては全ファイルが writable → `-not -writable` が何にもマッチせず **何も削除されない**。Clean workspace ステップは「成功」するが、実際には何もしていなかった。

**最終修正**: `sudo chown -R "$(id -u):$(id -g)"` で所有権をランナーユーザーに変更。`actions/checkout` が正常にクリーンアップ可能に。

変更ファイル（3つ全て同じ修正）:
- `.github/workflows/benchmark-rq2-01-setup.yml` — clean workspace ステップ新規追加
- `.github/workflows/benchmark-rq2-02-tools.yml` — `find -not -writable` → `chown -R` に修正
- `.github/workflows/benchmark-rq2-03-evaluate.yml` — clean workspace ステップ新規追加

```yaml
# 全3ワークフローの checkout 前に配置
- name: Clean workspace (fix Docker root-owned files)
  run: |
    if [ -d "${{ github.workspace }}" ]; then
      sudo chown -R "$(id -u):$(id -g)" "${{ github.workspace }}" 2>/dev/null || true
    fi
```

---

## 5. 未完了のタスク・次回やるべきこと

### 5.1 CI パーミッション修正の動作確認 ★最優先

`49bbed8` の `chown -R` 修正がプッシュ済み。次回 CI 実行（`benchmark-rq2-02-tools` ワークフロー）で `actions/checkout` が `__pycache__` で失敗しないことを確認する。

確認方法: GitHub Actions → workflow_dispatch で `benchmark-rq2-02-tools` を実行し、「Checkout Branch」ステップが成功するか確認。

### 5.2 `invoke_security_agent.sh` の本体実装

現在プレースホルダー。SPECA パイプラインの「単一ファイル監査モード」が完成したら、以下のような呼び出しに置き換える:

```bash
# 案: run_phase.py に --target-file モードを追加
uv run python -m scripts.run_phase --phase 03 \
  --target-file "${CODE_PATH}" \
  --output "${OUTPUT_PATH}" \
  --case-id "${CASE_ID}"
```

### 5.3 PR の作成

`claude/understand-project-overview-RPCCv` ブランチは push 済みだが、PR はまだ作成されていない。内容を確認して master へのマージ PR を作成する必要がある。15 コミット, 30 ファイル変更, +7246 行。

### 5.4 MCP セットアップ問題

ローカル環境で `bash scripts/setup_mcp.sh` が `claude` CLI not found で失敗する件。`npm install -g @anthropic-ai/claude-code` でインストールが必要。ただしテストやベンチマークの実行には MCP は不要。

### 5.5 LLM ベースライン結果の再取得

`benchmarks/results/rq2/primevul/llm_baseline_results.jsonl` は全件エラー（`"error": "..."` のみ）。CI で API キー付きで再実行が必要。

---

## 6. コーディング規約

### 6.1 言語・ランタイム

- **Python**: `>=3.11` 必須（`pyproject.toml` で指定）
- **パッケージマネージャ**: `uv`（pip/poetry ではない）
- **実行方法**: 常に `uv run python3 ...` を使う

### 6.2 コードスタイル

- **型ヒント**: `from __future__ import annotations` を使用
- **データモデル**: `pydantic>=2.0` で定義（`schemas.py`）
- **非同期**: `asyncio` ベース（orchestrator 全体）
- **linter/formatter**: 明示的な設定ファイル（`.flake8`, `ruff.toml` 等）はない。既存コードのスタイルに従うこと
- **テスト**: `pytest`。`tests/` ディレクトリに配置

### 6.3 ファイル命名規約

| 種類 | パターン | 例 |
|------|---------|-----|
| 出力 | `outputs/{phase_id}_{PREFIX}_PARTIAL_W{worker}B{batch}_{timestamp}.json` | `outputs/03_AUDITMAP_PARTIAL_W1B2_20260220.json` |
| キュー | `outputs/{phase_id}_QUEUE_{worker_id}.json` | `outputs/03_QUEUE_w1.json` |
| ログ | `outputs/logs/{phase_id}_W{worker}B{batch}_{timestamp}.jsonl` | |
| ベンチマーク結果 | `benchmarks/results/rq2/{dataset}/{tool}_results.json(l)` | `benchmarks/results/rq2/primevul/semgrep_results.json` |

### 6.4 スキル定義

- `.claude/skills/<name>/SKILL.md` に配置
- YAML フロントマター: `name`, `description`, `allowed-tools`, `context: fork`
- 純関数: JSON 入力 → JSON 出力

### 6.5 ワークフロー (GitHub Actions)

- パイプラインフェーズ: `.github/workflows/{phase_id}-{name}.yml`
- ベンチマーク: `.github/workflows/benchmark-rq{N}-{step}-{name}.yml`
- `self-hosted` ランナーを使用
- `uv sync --python 3.11` でセットアップ
- 結果は git push + artifact upload の両方で保存

### 6.6 設計原則（CLAUDE.md から）

1. **部分結果はファーストクラス**: バッチ結果は即座に保存。バリデーション失敗で保存をブロックしない
2. **サーキットブレーカーは共有**: 全ワーカーで1つ。システム障害時に高速停止
3. **MCP ファーストのコード解決**: Phase 02c/03 は `mcp__tree_sitter__get_symbols` / `run_query` を使う。直接ファイルアクセスは禁止
4. **予算管理は ClaudeRunner に組み込み**: 後付けではない。`BudgetExceeded` で即停止
5. **Phase 02c/03 のターゲット一貫性**: 02c が `outputs/02c_TARGET_INFO.json` を作成し、03 が自動で同じターゲットを使用

---

## 7. テストの実行方法

```bash
# 全テスト実行（必ず通ることを確認してから作業開始）
uv run python3 -m pytest tests/ -v --tb=short

# 現在の結果: 178 passed
```

---

## 8. よく使うコマンド

```bash
# 環境セットアップ
uv sync

# テスト
uv run python3 -m pytest tests/ -v --tb=short

# ベンチマーク（ローカル）
bash benchmarks/scripts/run_rq2_local.sh primevul semgrep

# パイプライン実行（MCP 必要）
uv run python3 scripts/run_phase.py --phase 01a

# MCP セットアップ
bash scripts/setup_mcp.sh
bash scripts/setup_mcp.sh --verify

# Git
git log --oneline -20
git diff master..HEAD --stat
```

---

## 9. 環境変数

| 変数 | 用途 | 必須場面 |
|------|------|---------|
| `KEYWORDS`, `SPEC_URLS` | Phase 01a（仕様発見）入力 | Phase 01a 実行時 |
| `FORCE_EXECUTE=1` | レジュームをバイパス | `--force` フラグで自動設定 |
| `CLAUDE_CODE_PERMISSIONS=bypassPermissions` | CI で権限確認スキップ | CI のみ |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS=100000` | CI 出力制限 | CI のみ |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub MCP サーバー用 | Phase 02, MCP セットアップ |
| `ANTHROPIC_API_KEY` | security_agent ベンチマーク | RQ2 ベンチマーク（security_agent 使用時） |
| `SA_COMMAND` | security_agent コマンドテンプレート | `run_rq2_local.sh` で security_agent 使用時 |

---

## 10. 既知の問題・注意点

1. **`generate_report.py`**: まだ存在するが、`--metrics` と `--output` を受け取る CLI であることは確認済み。中身は未読。動作確認は RQ2 実行時に行う
2. **`run_security_agent.py`**: `--command` テンプレートに `{code_path}`, `{output_path}`, `{case_id}` プレースホルダーを含む文字列を渡す設計。`invoke_security_agent.sh` がそのデフォルト実装
3. **Docker 必須**: Semgrep ランナーは Docker コンテナ内で実行される（`benchmarks/Dockerfile`）。Docker がない環境では Semgrep はスキップされる
4. **`sweagent` 依存**: `pyproject.toml` に git 依存として入っている。ネットワーク環境によっては `uv sync` が遅い/失敗する可能性あり
5. **Docker root ファイル問題**: Docker コンテナがデフォルトで root としてファイルを作成する。`--user "$(id -u):$(id -g)"` を指定しても `__pycache__` など Python が自動生成するファイルが残る場合がある。全 self-hosted ワークフローの checkout 前に `sudo chown -R` を入れること
6. **`sudo find -not -writable` は root で無効**: `sudo` で `find -not -writable` を実行すると root の視点で評価されるため、全ファイルが writable と判定される。所有権ベース（`chown`）または UID ベース（`-not -user $(id -u)`）で判定すること
