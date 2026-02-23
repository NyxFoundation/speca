# 引き継ぎ資料 — SPECA セキュリティエージェント

> 次回セッション開始時にこのファイルを読んで状況を把握してください。
> 最終更新: 2026-02-23

---

## 1. プロジェクト概要

**SPECA** (Specification-to-Property Agentic Auditing) は、Claude Code CLI を使った自動セキュリティ監査パイプラインです。仕様書からフォーマルなプログラムグラフ（Nielson & Nielson 形式）を構築し、Ethereum 特化 STRIDE 脅威モデルによるセキュリティプロパティを生成、ターゲットコードに対して3フェーズの形式的監査（抽象解釈→記号実行→不変条件証明）を実行します。

詳細は `CLAUDE.md`（リポジトリルート）を参照。

---

## 2. リポジトリ構成

```
security-agent/
├── CLAUDE.md                          # Claude Code 用プロジェクト規約（必読）
├── OPTIMIZATION_NOTES.md              # Phase 03 最適化詳細
├── pyproject.toml                     # Python 依存関係（uv, Python >=3.11）
├── conftest.py                        # pytest 設定
├── .mcp.json                          # MCP サーバー設定（tree_sitter, serena, semgrep, filesystem, fetch）
├── .claude/skills/                    # スキル定義（SKILL.md）
│   ├── spec-discovery/                # Phase 01a — URL クロール
│   ├── subgraph-extractor/            # Phase 01b — プログラムグラフ抽出
│   └── audit-reviewer/                # Phase 04 — 監査レビュー
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
│       ├── batch.py                   # バッチ戦略（トークンベース/件数ベース）
│       ├── queue.py                   # キュー管理
│       └── factory.py                 # オーケストレーター生成
├── prompts/                           # フェーズ別ワーカープロンプト
│   ├── 01a_crawl.md                   # 仕様書ディスカバリ
│   ├── 01b_extract_worker.md          # サブグラフ抽出
│   ├── 01e_prop_worker.md             # プロパティ生成（インライン、スキルフォークなし）
│   ├── 02c_codelocation_worker.md     # コード位置事前解決（インライン）
│   ├── 03_auditmap_worker_inline.md   # 3フェーズ形式的監査（インライン）
│   ├── 04_review_worker.md            # 監査レビュー
│   ├── 05_poc.md                      # PoC 生成（手動）
│   ├── 06_report.md                   # バグバウンティレポート（手動）
│   └── 06b_audit_report.md            # 完全監査レポート（手動）
├── outputs/                           # パイプライン出力（PARTIAL_*.json）
│   └── logs/                          # JSONL ストリームログ
├── tests/                             # pytest テスト（215件）
│   ├── test_schemas_and_config.py     # メインテスト（スキーマ、設定、回路遮断器、使用量制限検出）
│   ├── test_code_scope.py             # コードスコープ解決
│   ├── test_phase03_early_exit.py     # Phase 03 早期終了
│   ├── test_severity_gate.py          # 深刻度ゲート（Informational フィルタリング）
│   └── test_watchdog_cache_tokens.py  # キャッシュトークン追跡、予算制御
├── benchmarks/                        # ベンチマーク
│   ├── README.md                      # RQ1 & RQ2 評価方法論
│   ├── rq1/                           # RQ1: Sherlock 監査コンテスト評価
│   ├── rq2/                           # RQ2: PrimeVul ツール比較
│   │   ├── evaluate.py                # 修正済み（bootstrap_metric_diffs 引数追加）
│   │   └── generate_report.py
│   ├── runners/                       # ツール実行ラッパー
│   │   ├── run_semgrep.py
│   │   ├── run_codeql.py
│   │   ├── run_llm_baseline.py
│   │   ├── run_static_baseline.py
│   │   ├── run_security_agent.py
│   │   └── invoke_security_agent.sh   # プレースホルダー（本体未実装）
│   ├── scripts/
│   │   └── run_rq2_local.sh           # ローカル一括実行
│   ├── datasets/builders/             # データセットビルダー
│   ├── metrics/                       # 統計ユーティリティ（classification.py, stats.py）
│   ├── results/                       # ベンチマーク結果
│   └── tools/                         # ツールレジストリ・ローダー
├── .github/workflows/                 # CI/CD（14 ワークフロー）
│   ├── 01a-discovery.yml ... 04-audit-review.yml  # パイプラインフェーズ
│   ├── benchmark-rq1-sherlock-eval.yml             # RQ1 評価
│   ├── benchmark-rq2-01-setup.yml                  # RQ2 Step 1: データセット
│   ├── benchmark-rq2-02-tools.yml                  # RQ2 Step 2: ツール実行
│   └── benchmark-rq2-03-evaluate.yml               # RQ2 Step 3: 評価・レポート
└── docs/
    ├── hiro/
    │   ├── hikitugi.md                # ← この文書
    │   └── LOCAL_VERIFICATION_GUIDE.md # ローカル実行ガイド（日本語）
    ├── CLAUDE_CACHE_STRATEGY.md       # キャッシュ最適化ガイド
    ├── ethereum/                      # Ethereum 仕様・バグデータ
    └── report_templates/              # バグバウンティレポートテンプレート
```

---

## 3. パイプラインフロー

```
01a Spec Discovery       仕様書URLのクロール・発見
  ↓
01b Subgraph Extraction  仕様書 → Nielson & Nielson 形式的プログラムグラフ (.mmd)
  ↓
01e Property Generation  Ethereum 特化 STRIDE 脅威モデル + セキュリティプロパティ生成
  ↓                      ※ BUG_BOUNTY_SCOPE.json 必須（なければ sys.exit(1)）
02c Code Pre-resolution  Tree-sitter MCP でコード位置の事前解決（トークン 40-60% 削減）
  ↓                      ※ TARGET_INFO.json 必須（ワークフローが事前作成）
03  Audit Map            3段階フォーマル監査
  ↓                      Phase 1: 抽象解釈（状態異常検出）
  ↓                      Phase 2: 記号実行（具体的攻撃シナリオ構築）
  ↓                      Phase 3: 不変条件証明（ガード充足性の懐疑的検証）
04  Review               6カテゴリ判定
                         CONFIRMED_VULNERABILITY / LIKELY_VULNERABILITY /
                         VERIFIED_SAFE / FALSE_POSITIVE /
                         CODE_QUALITY_ISSUE / REQUIRES_MANUAL_REVIEW
--- 手動フェーズ ---
05  PoC Generation       脆弱性ごとの再現テスト生成
06  Bug-Bounty Report    プラットフォーム別レポート（Cantina, Code4rena, Ethereum, Immunefi, Sherlock）
06b Full Audit Report    出版可能な完全監査レポート
```

---

## 4. 現在のブランチ状態

| 項目 | 値 |
|------|-----|
| **作業ブランチ** | `work/20260223` |
| **ベースブランチ** | `master` |
| **master からの差分** | なし（master から分岐直後） |
| **テスト** | **215 passed** (全パス, 5.35s) |

### master の最新コミット（2026-02-21 以降）

| # | コミット | 内容 |
|---|---------|------|
| 1 | `939f385` | Dockerfile に PYTHONPATH 環境変数追加 |
| 2 | `6d03e79` | Docker root-owned ファイルパーミッションエラー修正 |
| 3 | `49bbed8` | `chown` による Docker クリーンアップ（`find -not -writable` 置換） |
| 4 | `2a97761` | PR #60 マージ（上記修正の統合） |

### アクティブな監査ブランチ（最新）

| ブランチ | ターゲット | 日付 |
|---------|-----------|------|
| `preresolve_prysm_fusaka-audit_238d5c07df_*` | OffchainLabs/prysm | 2026-02-22 |
| `ethereum-fusaka-20260220` | Ethereum クライアント群 | 2026-02-20 |
| `audit_go-ethereum_fusaka-audit_*` | go-ethereum | 2026-02-06 |
| `audit_lighthouse_fusaka-audit_*` | Lighthouse | 2026-02-04 |
| `audit_lodestar_fusaka-audit_*` | Lodestar | 2026-02-04 |

---

## 5. 前回セッション（2026-02-21）以降の変更

### 5.1 Docker インフラ修正

- **問題**: セルフホストランナーで Docker が root 所有ファイルを作成 → 次回ジョブの `git checkout` が権限エラーで失敗
- **修正**: `find -not -writable` を `sudo chown -R` に置換、`--user` フラグ追加
- **影響ファイル**: `.github/workflows/benchmark-rq2-02-tools.yml`, `Dockerfile`

### 5.2 Phase 01e プロパティ生成の強化

- **Ethereum 特化 STRIDE**: 汎用 STRIDE → Ethereum クライアント固有の脅威カテゴリに変更
  - ピア/バリデータなりすまし、ブロック/状態改竄、スラッシャブル違反、MEV/タイミングリーク、エクリプス/Blob スパム DoS、フォーク選択操作
- **実装ベースプロパティ**: 仕様レベルだけでなく、コード実装からもプロパティ生成が可能に
- **プロパティタイプ**: `invariant`, `threat`, `assumption`, `state_transition`, `optimization_correctness`

### 5.3 RQ1 ベンチマーク結果（Sherlock Ethereum 監査）

| 指標 | 値 |
|------|-----|
| **Issue Recall** | 0.273 (3/11 issues, Strict matching) |
| **マッチした脆弱性** | #40 Proposer 計算境界 (High), #203 Fiat-Shamir KZG 弱点 (High), #381 署名検証バイパス (Low) |
| **総 Findings** | 254 items（6 クライアント） |
| **新規/未マッチ** | 251（潜在的な新規脆弱性） |

---

## 6. 未完了のタスク・次回やるべきこと

### 6.1 `invoke_security_agent.sh` の本体実装（優先度: 中）

現在プレースホルダー。SPECA パイプラインの「単一ファイル監査モード」が完成したら実装:

```bash
uv run python -m scripts.run_phase --phase 03 \
  --target-file "${CODE_PATH}" \
  --output "${OUTPUT_PATH}" \
  --case-id "${CASE_ID}"
```

### 6.2 RQ2 ベンチマーク再実行（優先度: 高）

現状: Semgrep 0%, LLM Baseline 全エラー, CodeQL/Security Agent 未完了。CI パイプラインの修正は済んでいるので再実行が必要。

### 6.3 MCP セットアップ問題（優先度: 低）

ローカルで `bash scripts/setup_mcp.sh` が `claude` CLI not found で失敗する件。テストやベンチマークには不要。

---

## 7. コーディング規約

### 7.1 言語・ランタイム

- **Python**: `>=3.11` 必須（`pyproject.toml`）
- **パッケージマネージャ**: `uv`（pip/poetry ではない）
- **実行方法**: 常に `uv run python3 ...`

### 7.2 コードスタイル

- **型ヒント**: `from __future__ import annotations`
- **データモデル**: `pydantic>=2.0`（`schemas.py`）
- **非同期**: `asyncio` ベース（orchestrator 全体）
- **テスト**: `pytest`、`tests/` ディレクトリに配置

### 7.3 ファイル命名規約

| 種類 | パターン | 例 |
|------|---------|-----|
| 出力 | `outputs/{phase_id}_PARTIAL_W{worker}B{batch}_{timestamp}.json` | `03_AUDITMAP_PARTIAL_W1B2_20260220.json` |
| キュー | `outputs/{phase_id}_QUEUE_{worker_id}.json` | `03_QUEUE_w1.json` |
| ログ | `outputs/logs/{phase_id}_W{worker}B{batch}_{timestamp}.jsonl` | |
| ベンチマーク | `benchmarks/results/rq2/{dataset}/{tool}_results.json(l)` | `primevul/semgrep_results.json` |

### 7.4 設計原則（CLAUDE.md より）

1. **部分結果はファーストクラス** — バッチ結果は即座に保存。バリデーション失敗で保存をブロックしない
2. **サーキットブレーカーは共有** — 全ワーカーで1つ。システム障害時に高速停止
3. **MCP ファーストのコード解決** — Phase 02c は Tree-sitter MCP、Phase 03 は Read/Grep/Glob のみ
4. **予算管理は ClaudeRunner に組み込み** — `BudgetExceeded` で即停止
5. **Phase 02c/03 のターゲット一貫性** — `TARGET_INFO.json` を共有
6. **インラインプロンプト（01e, 02c, 03）** — スキルフォークなしでコンテキストオーバーヘッド削減

---

## 8. よく使うコマンド

```bash
# 環境セットアップ
uv sync

# テスト（全フェーズ実行前に必ず実施）
uv run python3 -m pytest tests/ -v --tb=short

# パイプライン実行
uv run python3 scripts/run_phase.py --phase 01a
uv run python3 scripts/run_phase.py --phase 01a 01b 01e
uv run python3 scripts/run_phase.py --target 04 --workers 4
uv run python3 scripts/run_phase.py --phase 03 --force --workers 4 --max-concurrent 64

# ベンチマーク（ローカル）
bash benchmarks/scripts/run_rq2_local.sh primevul semgrep

# MCP セットアップ
bash scripts/setup_mcp.sh
bash scripts/setup_mcp.sh --verify
```

---

## 9. 環境変数

| 変数 | 用途 | 必須場面 |
|------|------|---------|
| `KEYWORDS`, `SPEC_URLS` | Phase 01a 入力 | Phase 01a 実行時 |
| `FORCE_EXECUTE=1` | レジュームバイパス | `--force` で自動設定 |
| `CLAUDE_CODE_PERMISSIONS=bypassPermissions` | CI 権限スキップ | CI のみ |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS=100000` | CI 出力制限 | CI のみ |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub MCP | Phase 02, MCP セットアップ |
| `ANTHROPIC_API_KEY` | security_agent ベンチマーク | RQ2（security_agent 使用時） |
| `SA_COMMAND` | security_agent コマンドテンプレート | `run_rq2_local.sh` |

---

## 10. 既知の問題・注意点

1. **`invoke_security_agent.sh`**: 本体未実装。`"error": "not_implemented"` を返すのみ
2. **Docker 必須**: Semgrep ランナーは Docker コンテナ内実行。Docker なし環境ではスキップされる
3. **`sweagent` 依存**: `pyproject.toml` に git 依存あり。ネットワーク次第で `uv sync` が遅い/失敗する可能性
4. **RQ2 結果不完全**: 現在の結果は全ツール 0% recall。CI 修正済みだが再実行が必要
5. **テスト数の増加**: 178 → 215 に増加（使用量制限検出テスト、深刻度ゲートテスト等が追加）
