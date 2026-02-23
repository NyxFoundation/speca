# RQ2 ベンチマーク 実行・開発ガイド

> 最終更新: 2026-02-23
> 対象ディレクトリ: `benchmarks/rq2/`, `benchmarks/runners/`, `benchmarks/datasets/`, `.github/workflows/benchmark-rq2-*.yml`

---

## 進行状況

- [ ] Step 1: データセット取得の動作確認とキャッシュ整備
- [ ] Step 2: 静的ツールのベンチマーク実行とキャッシュ保存
- [ ] Step 3: security-agent のベンチマーク実行
- [ ] Step 4: 評価と結果の可視化
- [ ] Step 5: 再実験のフロー

---

## 1. RQ2 ベンチマークの概要

RQ2（Research Question 2）は、「security-agent が従来の静的解析ツールおよびファジングベースラインと比較して、ラベル付けされた脆弱性データセット上でどの程度の性能を発揮するか」を定量的に評価するベンチマークです。

### 1.1 評価対象データセット

| データセット | 言語 | 規模 | 取得元 | 用途 |
|---|---|---|---|---|
| **PrimeVul** | C/C++ | 868 サンプル (435 vulnerable) | Hugging Face | メインデータセット（デフォルト） |
| **CVEfixes** | C/C++, Java, Python 等 | 分散 OSS の CVE パッチ | Zenodo (v1.0.8) | 分散システム特化の補足評価 |
| **Vul4J** | Java | 数百件のペア | Zenodo | Java 特化の補足評価 |

各データセットは「脆弱なコード（vulnerable）」と「修正済みコード（clean）」のペアとして整形され、`pair_id` で紐付けられた JSONL 形式で保存されます。

### 1.2 評価対象ツール

| ツール名 | 種別 | 実行スクリプト | 結果ファイル |
|---|---|---|---|
| **semgrep** | 静的解析 | `runners/run_semgrep.py` | `semgrep_results.json` |
| **codeql** | 静的解析 | `runners/run_codeql.py` | `codeql_results.jsonl` |
| **security_agent** | LLM エージェント | `runners/run_security_agent.py` | `security_agent_results.jsonl` |
| **llm_baseline** | LLM ベースライン | `runners/run_llm_baseline.py` | `llm_baseline_results.jsonl` |
| **static_baseline** | 静的解析 (Infer 等) | `runners/run_static_baseline.py` | `static_baseline_results.jsonl` |

### 1.3 評価指標

`benchmarks/rq2/evaluate.py` が以下の指標を計算します。

| 指標 | 説明 |
|---|---|
| Precision / Recall / F1 | 標準的な二値分類指標 |
| Coverage | スコアリングされたサンプル数 / 全サンプル数 |
| Pairwise Accuracy | ペア単位の正解率（脆弱→True かつ clean→False の割合） |
| CWE Coverage | CWE カテゴリごとの再現率 |
| Unique Detections | security-agent のみが検出した脆弱性 |
| McNemar Exact Test | ツール間の有意差検定 |
| Cliff's Delta | 効果量（negligible / small / medium / large） |
| Bootstrap CI | 95% 信頼区間（2000 サンプル） |

**統計関数シグネチャ** (`benchmarks/metrics/stats.py`):

```python
def bootstrap_metric_diffs(
    tool_a: dict[str, bool | None],       # case_id -> prediction
    tool_b: dict[str, bool | None],       # case_id -> prediction
    ground_truth: dict[str, bool | None], # case_id -> label
    case_ids: list[str],                  # case IDs to sample from
    samples: int,                         # 2000
    seed: int,                            # 42
    ci_level: float                       # 0.95
) -> dict:  # {"accuracy": {...}, "precision": {...}, "recall": {...}, "f1": {...}}
```

### 1.4 キャッシュ設計

すべての中間成果物は `~/.cache/security-agent/` 以下に保存し、GitHub Actions では `actions/upload-artifact` / `actions/download-artifact` でアーティファクトとして管理します。

```
~/.cache/security-agent/
└── benchmarks/
    ├── primevul/
    │   └── primevul_test_paired.jsonl        # Step 1: データセット
    ├── cvefixes/
    │   └── CVEfixes.db                       # Step 1: CVEfixes DB
    ├── vul4j/
    │   └── vul4j_export.jsonl                # Step 1: Vul4J エクスポート
    └── results/
        └── {dataset}/
            ├── semgrep_results.json          # Step 2: 静的ツール結果
            ├── codeql_results.jsonl          # Step 2: 静的ツール結果
            ├── llm_baseline_results.jsonl    # Step 2: LLMベースライン結果
            ├── static_baseline_results.jsonl # Step 2: 静的ベースライン結果
            ├── security_agent_results.jsonl  # Step 3: security-agent 結果
            ├── evaluation_summary.json       # Step 4: 評価サマリー
            ├── metrics.json                  # Step 4: 詳細メトリクス
            └── report.md                     # Step 4: 可視化レポート
```

---

## 2. 現状の実装状況

### 2.1 実装済みのコンポーネント

以下のコンポーネントはコードとして実装されています。

| コンポーネント | ファイル | 状態 |
|---|---|---|
| PrimeVul ダウンロード | `datasets/builders/setup_benchmark.py` | 動作確認済み (870 行取得) |
| CVEfixes DB 取得 | `datasets/fetch_cvefixes.sh` | 実装済み |
| Vul4J 取得 | `datasets/fetch_vul4j.sh` | 実装済み |
| Semgrep ランナー | `runners/run_semgrep.py` | 動作確認済み (Docker 経由) |
| CodeQL ランナー | `runners/run_codeql.py` | 実装済み (clang/javac ビルド対応) |
| LLM ベースライン | `runners/run_llm_baseline.py` | 実装済み (claude CLI 経由) |
| 静的ベースライン | `runners/run_static_baseline.py` | 実装済み (Infer/SpotBugs) |
| 評価パイプライン | `rq2/evaluate.py` | 修正済み (bootstrap 引数追加) |
| レポート生成 | `rq2/generate_report.py` | 実装済み |
| CI: データセット準備 | `benchmark-rq2-01-setup.yml` | Artifact 保存対応済み |
| CI: ツール実行 | `benchmark-rq2-02-tools.yml` | security_agent 統合済み |
| CI: 評価 | `benchmark-rq2-03-evaluate.yml` | レポート生成・Artifact 対応済み |
| ローカル一括実行 | `scripts/run_rq2_local.sh` | 実装済み |

### 2.2 未実装・要修正の箇所

| 箇所 | 現状 | 必要な対応 |
|---|---|---|
| `invoke_security_agent.sh` | `"error": "not_implemented"` を返すのみ | security-agent 本体の呼び出しロジックを実装する |
| RQ2 結果の再実行 | Semgrep 0%, LLM 全エラー | CI 修正済みだが再実行が必要 |
| Docker パーミッション | `chown` 対応済みだが `--user` 未適用 | Semgrep Docker run に `--user $(id -u):$(id -g)` を付ける |

### 2.3 現在のベンチマーク結果

`benchmarks/results/rq2/` に以下が存在:

```
rq2/
├── metrics.json                    # 集計メトリクス
├── evaluation_summary.json         # 詳細評価（全ツール）
├── report.md                       # Markdown レポート
├── primevul/
│   ├── semgrep_results.json        # Semgrep 結果 (recall: 0%)
│   ├── semgrep_metadata.json
│   ├── llm_baseline_results.jsonl  # LLM 結果 (全エラー)
│   └── llm_baseline_metadata.json
└── figures/
    ├── fig1_tool_comparison.png
    ├── fig2_confusion_matrix.png
    ├── fig3_cwe_coverage.png
    ├── fig4_overview.png
    └── fig5_cwe_distribution.png
```

---

## 3. 進め方: ステップ別実行手順

### Step 1: データセット取得の動作確認とキャッシュ整備

#### 3.1.1 動作確認

```bash
cd /path/to/security-agent
uv sync --python 3.11
uv run python benchmarks/datasets/builders/setup_benchmark.py
```

正常に完了すると以下が生成されます:

- `benchmarks/data/primevul/primevul_test_paired.jsonl`（リポジトリ内）
- `~/.cache/security-agent/benchmarks/primevul/primevul_test_paired.jsonl`（キャッシュ）

**確認コマンド**:

```bash
# ファイルが存在し、JSONL 形式として正しく読めること
head -n 1 benchmarks/data/primevul/primevul_test_paired.jsonl | python3 -m json.tool
wc -l benchmarks/data/primevul/primevul_test_paired.jsonl  # → 870 行
ls -la ~/.cache/security-agent/benchmarks/primevul/primevul_test_paired.jsonl
```

| # | 確認内容 | 期待値 |
|---|---------|--------|
| 1 | ファイルが存在する | `primevul_test_paired.jsonl` がある |
| 2 | ファイルサイズ | 5MB 以上（小さすぎるとエラーページ） |
| 3 | 行数 | 870 行 |
| 4 | JSONL 形式 | `head -n 1` が valid JSON |
| 5 | キャッシュ | `~/.cache/...` にも同じファイルがある |

#### 3.1.2 GitHub Workflow の Artifact 保存（実装済み）

`benchmark-rq2-01-setup.yml` の末尾に以下が追加済み:

```yaml
      - name: Cache Dataset to Artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: rq2-dataset-${{ inputs.dataset }}-${{ github.run_id }}
          path: benchmarks/data/${{ inputs.dataset }}/
          retention-days: 30
          if-no-files-found: warn

      - name: Cache to ~/.cache
        run: |
          CACHE_DIR="${HOME}/.cache/security-agent/benchmarks/${{ inputs.dataset }}"
          mkdir -p "${CACHE_DIR}"
          cp -rf benchmarks/data/${{ inputs.dataset }}/. "${CACHE_DIR}/"
          echo "Cached to ${CACHE_DIR}"
```

#### 3.1.3 後続ワークフローの Artifact ダウンロード（実装済み）

`benchmark-rq2-02-tools.yml` に `dataset_run_id` 入力パラメータと Artifact ダウンロード + `~/.cache` フォールバックが追加済み。

---

### Step 2: 静的ツールのベンチマーク実行とキャッシュ保存

#### 3.2.1 Semgrep の動作確認

Semgrep は Docker コンテナ経由で実行されます。

```bash
# Docker イメージのビルド
docker build -t security-agent-benchmark -f benchmarks/Dockerfile .

# 動作確認
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD":/app -e PYTHONPATH=/app security-agent-benchmark \
  python3 /app/benchmarks/runners/run_semgrep.py \
    --dataset /app/benchmarks/data/primevul/primevul_test_paired.jsonl \
    --output /app/benchmarks/results/rq2/primevul/semgrep_results.json \
    --timeout 60
```

**確認ポイント**:
- `semgrep_results.json` と `semgrep_metadata.json` が生成されること
- 各レコードに `func_id` と `semgrep_findings` が含まれること

> **Docker パーミッション問題**: root 所有ファイルが生成される問題あり（後述セクション 5.1）

#### 3.2.2 CodeQL の動作確認

```bash
# デフォルトモード（codeql CLI が必要）
uv run python benchmarks/runners/run_codeql.py \
  --dataset benchmarks/data/primevul/primevul_test_paired.jsonl \
  --output benchmarks/results/rq2/primevul/codeql_results.jsonl \
  --tmp-dir benchmarks/tmp/codeql \
  --timeout 120
```

#### 3.2.3 LLM ベースラインの動作確認

```bash
# Claude CLI が必要
uv run python benchmarks/runners/run_llm_baseline.py \
  --dataset benchmarks/data/primevul/primevul_test_paired.jsonl \
  --output benchmarks/results/rq2/primevul/llm_baseline_results.jsonl \
  --tmp-dir benchmarks/tmp/llm_baseline \
  --timeout 60 \
  --limit 10  # まず 10 件でテスト
```

#### 3.2.4 結果のキャッシュ保存（CI 実装済み）

`benchmark-rq2-02-tools.yml` の末尾に `upload-artifact` + `~/.cache` 保存ステップが追加済み。

---

### Step 3: security-agent のベンチマーク実行

> **現状**: security-agent のトークン消費量問題を解決中のため、一旦スキップ可能。
> Step 4 は Step 3 のデータがなくても空の状態で進められます。

#### 3.3.1 `run_security_agent.py` の実装方針

現状の `run_security_agent.py` は `--command` 引数にコマンドテンプレートを渡すことで動作します。

**プレースホルダー**:

| プレースホルダー | 説明 |
|---|---|
| `{code_path}` | 解析対象コードファイルのパス |
| `{output_path}` | 予測結果を書き込む JSON ファイルのパス |
| `{case_id}` | サンプルの ID |

**出力ファイル形式** (`{output_path}` に書き込む JSON):

```json
{
  "predicted_vulnerable": true,
  "confidence": 0.85,
  "findings": 2,
  "spec": "Buffer overflow detected in function foo at line 42."
}
```

`predicted_vulnerable` フィールドが必須（`true` / `false`）。`spec` は任意だがユニーク検出例の表示に使用。

#### 3.3.2 security-agent 呼び出しスクリプト

`benchmarks/runners/invoke_security_agent.sh` は現在プレースホルダー:

```bash
#!/usr/bin/env bash
set -euo pipefail
CODE_PATH="$1"
OUTPUT_PATH="$2"
CASE_ID="$3"
# 本体未実装
echo '{"predicted_vulnerable": null, "error": "not_implemented"}' > "${OUTPUT_PATH}"
```

**実装時の呼び出し例**:

```bash
uv run python benchmarks/runners/run_security_agent.py \
  --dataset benchmarks/data/primevul/primevul_test_paired.jsonl \
  --output benchmarks/results/rq2/primevul/security_agent_results.jsonl \
  --tmp-dir benchmarks/tmp/security_agent \
  --command "bash benchmarks/runners/invoke_security_agent.sh {code_path} {output_path} {case_id}" \
  --shell \
  --timeout 300 \
  --limit 10  # まず 10 件でテスト
```

#### 3.3.3 実装に必要なもの

security-agent でベンチマークを実行するには、脆弱性データセットに加えて**対象 OSS の仕様書 URL**が必要。仕様書の取得方法も検討が必要。

---

### Step 4: 評価と結果の可視化

#### 3.4.1 評価の実行

```bash
# ローカルでの実行例
uv run python benchmarks/rq2/evaluate.py \
  --dataset primevul \
  --dataset-path benchmarks/data/primevul/primevul_test_paired.jsonl
```

**生成されるファイル**:

| ファイル | 内容 |
|---|---|
| `benchmarks/results/rq2/evaluation_summary.json` | 全ツールの詳細評価 (TP/FP/TN/FN, CWE カバレッジ) |
| `benchmarks/results/rq2/metrics.json` | 集計メトリクス |

#### 3.4.2 レポート生成

```bash
uv run python benchmarks/rq2/generate_report.py \
  --metrics benchmarks/results/rq2/metrics.json \
  --output benchmarks/results/rq2/report.md
```

CI (`benchmark-rq2-03-evaluate.yml`) ではこれらが自動実行され、`$GITHUB_STEP_SUMMARY` にレポート全文が表示されます。

---

### Step 5: 再実験のフロー

各ステップは独立して再実行可能です。

```
[Step 1] データセット取得
    ↓ (キャッシュあり → スキップ可)
[Step 2] 静的ツール実行 (semgrep, codeql, llm, static)
    ↓ (force_execute: false → 既存結果を使用)
[Step 3] security-agent 実行
    ↓ (force_execute: true → 強制再実行)
[Step 4] 評価・レポート生成
    ↓
[完了] report.md をアーティファクトとして確認
```

**security-agent のみ再実行する場合**:

1. `benchmark-rq2-02-tools.yml` を以下のパラメータで実行:
   - `tools`: `security_agent`
   - `force_execute`: `true`
   - `security_agent_command`: 新しいコマンドテンプレート
2. 完了後、`benchmark-rq2-03-evaluate.yml` を実行して評価を更新

**キャッシュを活用した部分再実行**:

```bash
# security-agent の結果のみ削除して再実行する例（ランナーホストで実行）
rm ~/.cache/security-agent/benchmarks/results/primevul/security_agent_results.jsonl
# その後、benchmark-rq2-02-tools.yml を tools: security_agent で実行
```

---

## 4. GitHub Workflow 全体設計

### 4.1 ワークフロー一覧と依存関係

```
benchmark-rq2-01-setup.yml
    │
    │ (Artifact: rq2-dataset-{dataset}-{run_id})
    ▼
benchmark-rq2-02-tools.yml
    │
    │ (Artifact: rq2-tool-results-{dataset}-{tools}-{run_id})
    ▼
benchmark-rq2-03-evaluate.yml
    │
    │ (Artifact: rq2-evaluation-{dataset}-{run_id})
    ▼
  report.md (GitHub Step Summary に表示)
```

### 4.2 各ワークフローの入力パラメータ

#### `benchmark-rq2-01-setup.yml`

| 入力 | 必須 | デフォルト | 説明 |
|---|---|---|---|
| `dataset` | No | `primevul` | 対象データセット (primevul/cvefixes/vul4j) |

#### `benchmark-rq2-02-tools.yml`

| 入力 | 必須 | デフォルト | 説明 |
|---|---|---|---|
| `branch` | No | 前ステップのブランチ | チェックアウトするブランチ |
| `dataset` | No | `primevul` | 対象データセット |
| `tools` | No | `all` | 実行ツール (カンマ区切り or `all`) |
| `tool_timeout` | No | `120` | ツール実行タイムアウト（秒） |
| `force_execute` | No | `false` | 既存結果を上書きするか |
| `dataset_run_id` | No | - | Step 1 の Run ID (Artifact ダウンロード用) |
| `security_agent_command` | No | `""` | security-agent コマンドテンプレート |

#### `benchmark-rq2-03-evaluate.yml`

| 入力 | 必須 | デフォルト | 説明 |
|---|---|---|---|
| `branch` | No | 前ステップのブランチ | チェックアウトするブランチ |
| `dataset` | No | `primevul` | 対象データセット |
| `tools_run_id` | No | - | Step 2 の Run ID (Artifact ダウンロード用) |
| `rq1_summary` | No | - | RQ1 サマリー JSON (統合レポート用) |

### 4.3 self-hosted ランナーの要件

すべてのワークフローは `runs-on: self-hosted` で実行されます。

| ツール | 用途 | インストール方法 |
|---|---|---|
| Docker | Semgrep の実行 | `apt-get install docker.io` |
| CodeQL CLI | CodeQL の実行 | [公式ドキュメント](https://docs.github.com/en/code-security/codeql-cli) |
| `uv` | Python 環境管理 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `clang` / `clang++` | CodeQL のビルド | `apt-get install clang` |
| `sqlite3` | CVEfixes DB の構築 | `apt-get install sqlite3` |

---

## 5. 既知の問題と対処方針

### 5.1 Docker root-owned ファイル問題

**現象**: self-hosted runner で 03. Audit Map 実行時、`actions/checkout@v4` のクリーンアップで `EACCES: permission denied, unlink benchmarks/__pycache__/__init__.cpython-311.pyc` が発生しジョブが停止する。

**再現手順**:
1. master ブランチで `benchmark-rq2-02-tools.yml`（RQ2 step2）を実行
2. 同じ runner ワークスペースで `03-audit-map.yml` を実行

**原因**: RQ2 step2 の Semgrep ステップで `docker run -v "$PWD":/app ...` を root ユーザのまま実行しており、コンテナ内で生成された `benchmarks/__pycache__/*.pyc` がホスト側で root 所有になる。次のジョブの checkout が削除できず失敗。

**影響範囲**: self-hosted runner 共有ワークスペース上のすべてのブランチ。

**暫定回避策**: ジョブ前に `sudo chown -R $USER:$USER "$RUNNER_WORKSPACE"` で所有権を戻してから実行。

**恒久対応案**: `benchmark-rq2-02-tools.yml` の Semgrep 実行ステップに `--user $(id -u):$(id -g)` を付ける:

```bash
UIDGID="$(id -u):$(id -g)"
docker run --rm --user "$UIDGID" -v "$PWD":/app security-agent-benchmark \
  python3 /app/benchmarks/runners/run_semgrep.py \
    --dataset "/app/${DATASET_PATH}" \
    --output "/app/${RESULTS_DIR}/semgrep_results.json" \
    --timeout "${{ inputs.tool_timeout }}"
```

> エフェメラル runner 運用や定期的なワークスペース掃除でも再発防止可能。

### 5.2 `evaluate.py` の `bootstrap_metric_diffs` 呼び出し

**状態**: 修正済み。evaluate.py:344 に `samples=BOOTSTRAP_SAMPLES`, `seed=BOOTSTRAP_SEED`, `ci_level=CI_LEVEL` を追加済み。

### 5.3 PrimeVul の `func_hash` vs `id` の不整合

`run_semgrep.py` は `func_hash` をキーとして使用するが、`evaluate.py` は `id` や `func_hash` など複数のキーを試みる。`bench_utils.py` の `extract_id` 関数が `func_hash` を含む `ID_KEYS` タプルを参照しているため基本的には問題なし。ただし Semgrep の結果ファイルの `func_id` キーが `evaluate.py` の `load_semgrep_results` で正しく処理されることを確認すること。

### 5.4 `security_agent` の実行時間

PrimeVul の全件（868 件）に対して security-agent を実行すると非常に長い時間がかかる。初期実験では `--limit` オプションで件数を制限し、段階的にスケールアップすることを推奨。

### 5.5 RQ2 結果の再実行が必要

現在の結果: Semgrep recall 0%, LLM baseline 全エラー (20 件)。CI パイプラインの修正（Docker PYTHONPATH、Artifact 管理等）は完了済みのため、再実行すれば改善する見込み。

---

## 6. ローカルでの一括実行

```bash
# デフォルト: PrimeVul, Semgrep のみ
bash benchmarks/scripts/run_rq2_local.sh

# 全ツール, 100 サンプル制限
bash benchmarks/scripts/run_rq2_local.sh primevul all 100

# 特定ツールの組み合わせ
bash benchmarks/scripts/run_rq2_local.sh primevul semgrep,codeql
```

**スクリプト内部のフロー**:

```
Step 1: データセット取得 (setup_benchmark.py) — キャッシュあればスキップ
    ↓
Step 2: ツール実行 (Docker/uv) — 既存結果あればスキップ
    ↓
Step 3: 評価 (evaluate.py)
    ↓
Step 4: レポート生成 (generate_report.py)
    ↓
Step 5: キャッシュ保存 (~/.cache/security-agent/)
```

---

## 7. ランナー共通インフラ

### 7.1 `base_runner.py` のインターフェース

すべてのランナーは共通のインフラを使用:

```python
@dataclass
class CommandSpec:
    dataset: str         # データセットパス
    output: str          # 出力ファイルパス
    tmp_dir: str         # 一時ディレクトリ
    command: str         # コマンドテンプレート
    timeout: int         # タイムアウト（秒）
    use_shell: bool      # シェル経由実行
    limit: int           # サンプル数制限 (0=無制限)
    tool_name: str       # ツール名
```

### 7.2 ツールレジストリ (`benchmarks/tools/registry.py`)

```python
TOOL_REGISTRY = {
    "semgrep":         ToolSpec("semgrep",         ("semgrep_results.json",),   load_semgrep_results),
    "codeql":          ToolSpec("codeql",           ("codeql_results.jsonl",),   load_jsonl_predictions),
    "security_agent":  ToolSpec("security_agent",   ("security_agent_results.json", "...jsonl"), load_jsonl_predictions),
    "llm_baseline":    ToolSpec("llm_baseline",     ("llm_baseline_results.jsonl",), load_jsonl_predictions),
    "static_baseline": ToolSpec("static_baseline",  ("static_baseline_results.jsonl",), load_jsonl_predictions),
}
```

### 7.3 データセットレジストリ (`benchmarks/datasets/registry.py`)

```python
DATASET_REGISTRY = {
    "primevul":  DatasetSpec("primevul",  Path("benchmarks/data/primevul/primevul_test_paired.jsonl")),
    "cvefixes":  DatasetSpec("cvefixes",  Path("benchmarks/data/cvefixes/cvefixes_subset_paired.jsonl")),
    "vul4j":     DatasetSpec("vul4j",     Path("benchmarks/data/vul4j/vul4j_paired.jsonl")),
}
```

---

## 8. 参考リンク

| ファイル | 説明 |
|---|---|
| `benchmarks/README.md` | RQ1/RQ2 の概要と実行方法 |
| `benchmarks/rq2/evaluate.py` | 評価ロジックの実装 |
| `benchmarks/rq2/generate_report.py` | レポート生成の実装 |
| `benchmarks/runners/base_runner.py` | ランナー共通ヘルパー (CommandSpec, run_command) |
| `benchmarks/bench_utils.py` | ID/ラベル/コード抽出ユーティリティ |
| `benchmarks/tools/registry.py` | ツールレジストリ（結果ファイルのパス解決） |
| `benchmarks/datasets/registry.py` | データセットレジストリ |
| `benchmarks/metrics/classification.py` | 分類指標の計算 (compute_confusion) |
| `benchmarks/metrics/stats.py` | 統計検定・ブートストラップ CI |
| `benchmarks/Dockerfile` | Semgrep 実行用 Docker イメージ (Python 3.11-slim) |
