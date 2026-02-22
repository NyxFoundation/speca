# SPECA ローカル手動確認ガイド

ローカル環境でパイプラインの各フェーズを手動で実行・確認するための手順書。

---

## 目次

1. [環境セットアップ](#1-環境セットアップ)
2. [事前チェック（Pre-flight）](#2-事前チェックpre-flight)
3. [フェーズ別 実行・確認手順](#3-フェーズ別-実行確認手順)
4. [出力ファイルの検証方法](#4-出力ファイルの検証方法)
5. [手動フェーズ（05・06・06b）](#5-手動フェーズ050606b)
6. [トラブルシューティング](#6-トラブルシューティング)

---

## 1. 環境セットアップ

### 1.1 前提条件のインストール

```bash
# Python 3.11+
python3 --version  # >= 3.11 を確認

# uv（Python パッケージマネージャ）
curl -LsSf https://astral.sh/uv/install.sh | sh

# Node.js & npm
node --version     # >= 18 を推奨
npm --version

# Claude Code CLI
npm install -g @anthropic-ai/claude-code
claude --version
```

### 1.2 Python 依存パッケージのインストール

```bash
cd /path/to/security-agent
uv sync
```

### 1.3 MCP サーバーの登録

```bash
# 全サーバーを登録
bash scripts/setup_mcp.sh

# 登録状態を確認
bash scripts/setup_mcp.sh --verify
```

**確認ポイント:**
- 6 つのサーバーすべてが `[OK]` と表示されること
  - `tree_sitter`, `serena`, `semgrep`, `filesystem`, `fetch`, `github`
- GitHub API を使うフェーズ (02) では `GITHUB_PERSONAL_ACCESS_TOKEN` が必要

### 1.4 環境変数の設定

```bash
# Phase 01a に必要
export KEYWORDS="geth,ethereum client,execution specs,EIP"
export SPEC_URLS="https://ethereum.github.io/execution-specs/src/,https://geth.ethereum.org/docs"

# GitHub MCP（任意）
export GITHUB_PERSONAL_ACCESS_TOKEN="ghp_..."
```

---

## 2. 事前チェック（Pre-flight）

**すべてのフェーズ実行前に必ず実施する。**

```bash
uv run python3 -m pytest tests/ -v --tb=short
```

**確認ポイント:**
- 全テストが `PASSED` であること
- スキーマ定義（`test_schemas_and_config.py`）が通ること
- Phase 03 の早期終了ロジック（`test_phase03_early_exit.py`）が通ること

---

## 3. フェーズ別 実行・確認手順

### パイプライン依存関係

```
01a → 01b → 01c（検証）
              └→ 01d（Trust Model）→ 01e → 02 → 02c → 03 → 04
```

> 01c と 01d は並列実行可能。01e は 01d に依存。

---

### Phase 01a: 仕様書ディスカバリ

**実行:**
```bash
uv run python3 scripts/run_phase.py --phase 01a
```

**出力ファイル:** `outputs/01a_STATE.json`

**手動確認項目:**

| # | 確認内容 | 方法 |
|---|---------|------|
| 1 | ファイルが生成されている | `ls -la outputs/01a_STATE.json` |
| 2 | JSON が valid | `python3 -m json.tool outputs/01a_STATE.json > /dev/null` |
| 3 | `found_specs` 配列が空でない | `python3 -c "import json; d=json.load(open('outputs/01a_STATE.json')); print(f'Specs: {len(d[\"found_specs\"])}')"` |
| 4 | 各 spec に `url` フィールドがある | 目視で確認 |
| 5 | URL が実際にアクセス可能 | 代表的な URL をブラウザで開く |

---

### Phase 01b: サブグラフ抽出

**実行:**
```bash
uv run python3 scripts/run_phase.py --phase 01b --workers 2
```

**出力ファイル:** `outputs/graphs/*/index.json` + `*.mmd`

**手動確認項目:**

| # | 確認内容 | 方法 |
|---|---------|------|
| 1 | `outputs/graphs/` 配下にディレクトリが生成されている | `ls outputs/graphs/` |
| 2 | 各ディレクトリに `index.json` がある | `find outputs/graphs -name index.json` |
| 3 | Mermaid ファイル（`.mmd`）が生成されている | `find outputs/graphs -name "*.mmd"` |
| 4 | プログラムグラフ構造が正しい | `index.json` の各グラフに `Q`, `q_init`, `q_final`, `Act`, `E` が含まれること |
| 5 | エッジが `[source, action, target]` 形式 | `E` 配列の各要素が 3 要素リストであること |

```bash
# グラフ構造のクイック検証
python3 -c "
import json, glob
for f in glob.glob('outputs/graphs/*/index.json'):
    data = json.load(open(f))
    specs = data.get('specs', [data]) if isinstance(data, dict) else data
    print(f'{f}: OK')
"
```

---

### Phase 01c: サブグラフ検証

**実行:**
```bash
uv run python3 scripts/run_phase.py --phase 01c --workers 2
```

**出力ファイル:** `outputs/01c_PARTIAL_*.json`

**手動確認項目:**

| # | 確認内容 | 方法 |
|---|---------|------|
| 1 | PARTIAL ファイルが生成されている | `ls outputs/01c_PARTIAL_*.json` |
| 2 | 検証結果に `file_path` と `status` がある | 目視で確認 |
| 3 | 重大な検証エラーがない | `status` が `valid` / `warning` であること |

---

### Phase 01d: Trust Model 分析

**実行:**
```bash
uv run python3 scripts/run_phase.py --phase 01d --workers 2
```

**出力ファイル:** `outputs/01d_PARTIAL_*.json`

**手動確認項目:**

| # | 確認内容 | 方法 |
|---|---------|------|
| 1 | PARTIAL ファイルが生成されている | `ls outputs/01d_PARTIAL_*.json` |
| 2 | Trust Model にアクター定義がある | `actors` 配列が空でないこと |
| 3 | Trust Boundary が定義されている | `boundaries` 配列が空でないこと |
| 4 | Bug Bounty スコープが付与されている | 各要素に `bug_bounty_scope` があること |

---

### Phase 01e: プロパティ生成

**実行:**
```bash
uv run python3 scripts/run_phase.py --phase 01e --workers 2
```

**出力ファイル:** `outputs/01e_PARTIAL_*.json`

**手動確認項目:**

| # | 確認内容 | 方法 |
|---|---------|------|
| 1 | PARTIAL ファイルが生成されている | `ls outputs/01e_PARTIAL_*.json` |
| 2 | 各プロパティに `property_id` がある | ユニークな ID があること |
| 3 | `invariant` と `anti_property` が定義されている | 形式的な不変条件と反例が記述されていること |
| 4 | `severity` が定義されている | `Critical` / `High` / `Medium` / `Low` / `Informational` のいずれか |
| 5 | `reachability` が設定されている | `external-reachable` / `internal-only` / `api-only` のいずれか |

---

### Phase 02: チェックリスト生成

**実行:**
```bash
uv run python3 scripts/run_phase.py --phase 02 --workers 2
```

**出力ファイル:** `outputs/02_PARTIAL_*.json`

**手動確認項目:**

| # | 確認内容 | 方法 |
|---|---------|------|
| 1 | PARTIAL ファイルが生成されている | `ls outputs/02_PARTIAL_*.json` |
| 2 | 各アイテムに `check_id` がある | ユニークな ID があること |
| 3 | `severity` が適切 | 上流プロパティの severity と整合すること |
| 4 | `property_id` で上流とリンクしている | 01e の property_id が参照されていること |
| 5 | チェック内容が具体的 | 曖昧な記述でないこと（目視確認） |

---

### Phase 02c: コード位置の事前解決

**実行:**
```bash
uv run python3 scripts/run_phase.py --phase 02c --workers 2
```

**出力ファイル:** `outputs/02c_PARTIAL_*.json`, `outputs/02c_TARGET_INFO.json`

**手動確認項目:**

| # | 確認内容 | 方法 |
|---|---------|------|
| 1 | `02c_TARGET_INFO.json` が生成されている | `ls outputs/02c_TARGET_INFO.json` |
| 2 | ターゲットリポジトリ情報が正しい | `target_repo`, `target_ref` を目視確認 |
| 3 | PARTIAL ファイルが生成されている | `ls outputs/02c_PARTIAL_*.json` |
| 4 | `code_scope` にファイルパスがある | 各アイテムの `code_scope.file_path` を確認 |
| 5 | `code_excerpt` にコード断片がある | 空でないこと |
| 6 | `out_of_scope` アイテムが合理的 | スコープ外の理由が妥当であること |

---

### Phase 03: フォーマル監査（3 フェーズ統合）

**実行:**
```bash
uv run python3 scripts/run_phase.py --phase 03 --workers 4 --max-concurrent 64
```

**出力ファイル:** `outputs/03_PARTIAL_*.json`

**手動確認項目:**

| # | 確認内容 | 方法 |
|---|---------|------|
| 1 | PARTIAL ファイルが生成されている | `ls outputs/03_PARTIAL_*.json` |
| 2 | 3 フェーズすべての結果がある | 各アイテムに `phase1`（抽象解釈）、`phase2`（記号実行）、`phase3`（不変条件証明）があること |
| 3 | `classification` が適切 | `vulnerable` / `safe` / `inconclusive` / `out-of-scope` のいずれか |
| 4 | 早期終了アイテムが妥当 | `safe` で Phase 2/3 がスキップされたものの理由が合理的であること |
| 5 | 脆弱性報告にコード参照がある | `vulnerable` なアイテムにファイルパスと行番号があること |
| 6 | サーキットブレーカーが発動していない | ログに `CircuitBreaker` エラーがないこと |

```bash
# 監査結果の統計
python3 -c "
import json, glob, collections
counts = collections.Counter()
for f in glob.glob('outputs/03_PARTIAL_*.json'):
    data = json.load(open(f))
    items = data.get('audit_items', data.get('items', []))
    for item in items:
        counts[item.get('classification', 'unknown')] += 1
for k, v in counts.most_common():
    print(f'  {k}: {v}')
print(f'  Total: {sum(counts.values())}')
"
```

---

### Phase 04: 監査レビュー

**実行:**
```bash
uv run python3 scripts/run_phase.py --phase 04 --workers 2
```

**出力ファイル:** `outputs/04_PARTIAL_*.json`

**手動確認項目:**

| # | 確認内容 | 方法 |
|---|---------|------|
| 1 | PARTIAL ファイルが生成されている | `ls outputs/04_PARTIAL_*.json` |
| 2 | 6 カテゴリの verdict が付与されている | `Confirmed` / `Disputed` / `Needs More Info` 等 |
| 3 | `check_id` で Phase 03 とリンクしている | Phase 03 のアイテムと対応していること |
| 4 | 信頼度スコアがある | `confidence` フィールドが設定されていること |
| 5 | Confirmed 脆弱性の根拠が明確 | 目視で判定理由を確認 |

```bash
# レビュー結果のサマリ
python3 -c "
import json, glob, collections
verdicts = collections.Counter()
for f in glob.glob('outputs/04_PARTIAL_*.json'):
    data = json.load(open(f))
    items = data.get('reviewed_items', data.get('items', []))
    for item in items:
        verdicts[item.get('verdict', 'unknown')] += 1
for k, v in verdicts.most_common():
    print(f'  {k}: {v}')
print(f'  Total: {sum(verdicts.values())}')
"
```

---

## 4. 出力ファイルの検証方法

### 4.1 JSON バリデーション（全フェーズ共通）

```bash
# 全 PARTIAL ファイルの JSON 構文チェック
for f in outputs/*PARTIAL*.json; do
  python3 -m json.tool "$f" > /dev/null 2>&1 && echo "OK: $f" || echo "INVALID: $f"
done
```

### 4.2 Pydantic スキーマ検証

```bash
# テストスイートで全スキーマをバリデーション
uv run python3 -m pytest tests/test_schemas_and_config.py -v --tb=short
```

### 4.3 フェーズ間の ID 整合性チェック

```bash
python3 -c "
import json, glob

# Phase 01e → 02 の property_id リンク確認
prop_ids = set()
for f in glob.glob('outputs/01e_PARTIAL_*.json'):
    data = json.load(open(f))
    for item in data.get('properties', data.get('items', [])):
        prop_ids.add(item.get('property_id', ''))

checklist_refs = set()
for f in glob.glob('outputs/02_PARTIAL_*.json'):
    data = json.load(open(f))
    for item in data.get('checklist', data.get('items', [])):
        checklist_refs.add(item.get('property_id', ''))

orphans = checklist_refs - prop_ids
if orphans:
    print(f'WARNING: {len(orphans)} checklist items reference unknown property_ids')
else:
    print('OK: All property_id references are valid')
"
```

### 4.4 ログの確認

```bash
# 直近のログを確認
ls -lt outputs/logs/ | head -20

# エラーが含まれるログを検索
grep -l '"error"' outputs/logs/*.jsonl 2>/dev/null || echo "No errors found"

# サーキットブレーカーの発動を確認
grep -l 'circuit_breaker\|CircuitBreaker' outputs/logs/*.jsonl 2>/dev/null || echo "No circuit breaker events"
```

---

## 5. 手動フェーズ（05・06・06b）

これらは Claude Code CLI で対話的に実行する。オーケストレータは使用しない。

### Phase 05: PoC 生成

```bash
# Claude Code を起動して skill を使う
claude

# Claude Code 内で:
# /formal-audit-unified の結果から脆弱性を選び PoC を生成
# prompts/05_poc.md の手順に従う
```

**確認ポイント:**
- PoC コードがビルド・実行可能であること
- 脆弱性の再現手順が明確であること
- false positive でないことの根拠があること

### Phase 06: バグバウンティレポート

```bash
# Claude Code 内で prompts/06_report.md に従い実行
# テンプレート: docs/report_templates/ 配下
```

**確認ポイント:**
- レポートテンプレートが正しく埋められていること
- 深刻度の根拠が明記されていること
- 再現手順が第三者に理解可能であること

### Phase 06b: 完全監査レポート

```bash
# Claude Code 内で prompts/06b_audit_report.md に従い実行
```

**確認ポイント:**
- 11 セクション構成が守られていること
- リポジトリ固有の内部 ID がサニタイズされていること
- すべての Confirmed 脆弱性が記載されていること

---

## 6. トラブルシューティング

### 6.1 よくある問題

| 症状 | 原因 | 対処 |
|------|------|------|
| `Missing input: outputs/01a_STATE.json` | 前段フェーズ未実行 | 依存フェーズを先に実行する |
| `CircuitBreaker tripped` | 連続バッチ失敗 | ログを確認し、プロンプトや MCP サーバーの問題を修正 |
| `BudgetExceeded` | フェーズ予算超過 | `config.py` の `max_budget_usd` を確認。不要な再実行を避ける |
| MCP サーバー接続エラー | サーバー未登録/起動失敗 | `bash scripts/setup_mcp.sh --verify` で確認 |
| 空の PARTIAL ファイル | LLM が結果を返さなかった | `--force` で再実行 or バッチサイズを減らす |

### 6.2 レジューム（中断からの再開）

```bash
# 前回の途中から再開（デフォルト動作）
uv run python3 scripts/run_phase.py --phase 03 --workers 4

# 完了済みアイテムを無視して全件再実行
uv run python3 scripts/run_phase.py --phase 03 --force --workers 4
```

### 6.3 不完全バッチのクリーンアップ

```bash
# ドライラン（削除されるファイルを確認のみ）
uv run python3 scripts/run_phase.py --phase 03 --cleanup-dry-run

# 実行（不完全バッチとログを削除）
uv run python3 scripts/run_phase.py --phase 03 --cleanup
```

### 6.4 コスト確認

ログファイル内のトークン使用量から概算コストを確認:

```bash
# Phase 03 の直近ログからトークン使用量を集計
python3 -c "
import json, glob
total_input = total_output = 0
for f in sorted(glob.glob('outputs/logs/03_*.jsonl')):
    for line in open(f):
        try:
            entry = json.loads(line)
            usage = entry.get('usage', {})
            total_input += usage.get('input_tokens', 0)
            total_output += usage.get('output_tokens', 0)
        except: pass
print(f'Input tokens:  {total_input:,}')
print(f'Output tokens: {total_output:,}')
"
```

---

## 7. RQ2 ベンチマーク: データセット取得とキャッシュの確認

### 7.1 やったことの説明

RQ2 ベンチマークでは「セキュリティツール（Semgrep、CodeQL など）がどれくらい脆弱性を検出できるか」を比較評価します。
そのためにまずテスト用のデータセット（PrimeVul）をダウンロードする必要があります。

この作業では以下の **3 つのこと** を行いました:

#### (1) データセット取得スクリプトの動作確認
`setup_benchmark.py` というスクリプトが、PrimeVul データセットを Hugging Face からダウンロードします。
ローカルで実行し、ファイルが正しく取得されることを確認しました。

```
取得先 URL → ダウンロード → benchmarks/data/primevul/primevul_test_paired.jsonl に保存
                          → ~/.cache/security-agent/benchmarks/primevul/ にもキャッシュ
```

#### (2) GitHub Actions ワークフロー 01（セットアップ）に「Artifact 保存」を追加
GitHub Actions で CI を回すとき、ダウンロードしたデータセットを **Artifact**（GitHub が提供する一時ファイル保存機能）として 30 日間保存するようにしました。
こうすると、次のワークフローでわざわざ再ダウンロードしなくて済みます。

**変更ファイル:** `.github/workflows/benchmark-rq2-01-setup.yml`

**追加したステップ:**
- `Cache Dataset to Artifact` — データセットを GitHub Artifact にアップロード
- `Cache to ~/.cache` — ランナーのローカルキャッシュにもコピー
- Summary にアーティファクト名を表示（次のワークフローで使う Run ID がわかる）

#### (3) GitHub Actions ワークフロー 02（ツール実行）に「Artifact ダウンロード」を追加
ツール実行ワークフローが始まるとき、ワークフロー 01 で保存した Artifact からデータセットを取得します。
Artifact が見つからない場合は `~/.cache` から復元するフォールバック機能も追加しました。

**変更ファイル:** `.github/workflows/benchmark-rq2-02-tools.yml`

**追加したもの:**
- `dataset_run_id` 入力パラメータ — ワークフロー 01 の Run ID を指定
- `Download Dataset Artifact` ステップ — Artifact からデータセットをダウンロード
- `Fallback to ~/.cache` ステップ — Artifact が無い場合のフォールバック

```
ワークフロー全体の流れ:

  [01-setup] データセットDL → Git push → Artifact保存 → ~/.cache保存
                                              ↓
  [02-tools] Artifactダウンロード（or ~/.cache復元）→ ツール実行 → 結果push
                                              ↓
  [03-evaluate] 結果を集計・評価
```

---

### 7.2 ローカルでの手動検証手順

#### ステップ 1: データセット取得スクリプトの動作確認

```bash
cd /path/to/security-agent
uv sync --python 3.11
uv run python benchmarks/datasets/builders/setup_benchmark.py
```

**確認コマンド:**

```bash
# ファイルが存在するか
ls -la benchmarks/data/primevul/primevul_test_paired.jsonl

# 行数の確認（数百行以上あれば正常）
wc -l benchmarks/data/primevul/primevul_test_paired.jsonl

# JSONL 形式として先頭行が読めるか
head -n 1 benchmarks/data/primevul/primevul_test_paired.jsonl | python3 -m json.tool

# キャッシュにもコピーされているか
ls -la ~/.cache/security-agent/benchmarks/primevul/primevul_test_paired.jsonl
```

**期待される結果:**

| # | 確認内容 | 期待値 |
|---|---------|--------|
| 1 | ファイルが存在する | `primevul_test_paired.jsonl` がある |
| 2 | ファイルサイズ | 5MB 以上（小さすぎるとエラーページの可能性） |
| 3 | 行数 | 870 行 |
| 4 | JSONL 形式 | `head -n 1` が valid JSON として表示される |
| 5 | キャッシュ | `~/.cache/...` にも同じファイルがある |

#### ステップ 2: ワークフロー YAML の変更確認

```bash
# 変更差分を確認
git diff HEAD~1 -- .github/workflows/benchmark-rq2-01-setup.yml
git diff HEAD~1 -- .github/workflows/benchmark-rq2-02-tools.yml
```

**01-setup.yml の確認ポイント:**

| # | 確認内容 | 確認方法 |
|---|---------|---------|
| 1 | `Cache Dataset to Artifact` ステップがある | `grep "Cache Dataset to Artifact" .github/workflows/benchmark-rq2-01-setup.yml` |
| 2 | `actions/upload-artifact@v4` を使っている | `grep "upload-artifact" .github/workflows/benchmark-rq2-01-setup.yml` |
| 3 | 保持期間が 30 日 | `grep "retention-days: 30" .github/workflows/benchmark-rq2-01-setup.yml` |
| 4 | `Cache to ~/.cache` ステップがある | `grep "Cache to" .github/workflows/benchmark-rq2-01-setup.yml` |
| 5 | Summary にアーティファクト名が表示される | `grep "Dataset artifact" .github/workflows/benchmark-rq2-01-setup.yml` |

**02-tools.yml の確認ポイント:**

| # | 確認内容 | 確認方法 |
|---|---------|---------|
| 1 | `dataset_run_id` 入力パラメータがある | `grep "dataset_run_id" .github/workflows/benchmark-rq2-02-tools.yml` |
| 2 | `Download Dataset Artifact` ステップがある | `grep "Download Dataset Artifact" .github/workflows/benchmark-rq2-02-tools.yml` |
| 3 | `continue-on-error: true` が設定されている | Artifact が無くてもエラーにならない |
| 4 | `Fallback to ~/.cache` ステップがある | `grep "Fallback" .github/workflows/benchmark-rq2-02-tools.yml` |
| 5 | Verify Dataset がフォールバックの後にある | ダウンロード → フォールバック → 検証 の順序 |

#### ステップ 3: ワークフローのステップ順序確認

```bash
# 01-setup のステップ一覧（順序確認）
grep "name:" .github/workflows/benchmark-rq2-01-setup.yml
```

期待される順序:
```
1. Checkout Repository
2. Validate Dataset Selection
3. Setup Python (uv)
4. Fetch CVEfixes Cache (optional)
5. Fetch Vul4J Cache (optional)
6. Prepare Git & Branch
7. Download Benchmark Dataset
8. Prepare CVEfixes Subset
9. Prepare Vul4J Dataset
10. Push Dataset
11. Cache Dataset to Artifact     ← 追加
12. Cache to ~/.cache             ← 追加
13. Summary                       ← アーティファクト名追加
```

```bash
# 02-tools のステップ一覧（順序確認）
grep "name:" .github/workflows/benchmark-rq2-02-tools.yml
```

期待される順序:
```
1. Checkout Branch
2. Validate Dataset Selection
3. Resolve Dataset Paths
4. Download Dataset Artifact      ← 追加
5. Fallback to ~/.cache           ← 追加
6. Verify Dataset
7. Setup Python (uv)
8. ... (ツール実行ステップ)
```

---

## チェックリスト: 全フェーズ完了確認

```
[ ] 環境セットアップ完了（Python, uv, Node.js, Claude CLI, MCP）
[ ] Pre-flight テスト全件 PASSED
[ ] Phase 01a: outputs/01a_STATE.json 生成・仕様書 URL 確認
[ ] Phase 01b: outputs/graphs/ にグラフ生成確認
[ ] Phase 01c: サブグラフ検証 PASSED
[ ] Phase 01d: Trust Model 生成・アクター/境界定義確認
[ ] Phase 01e: セキュリティプロパティ生成確認
[ ] Phase 02:  チェックリスト生成・ID リンク確認
[ ] Phase 02c: コード位置解決・TARGET_INFO 確認
[ ] Phase 03:  3 フェーズ監査完了・分類結果確認
[ ] Phase 04:  レビュー verdict 付与・最終判定確認
[ ] フェーズ間 ID 整合性チェック OK
[ ] ログにサーキットブレーカー/予算超過エラーなし
[ ] RQ2: setup_benchmark.py で primevul_test_paired.jsonl 取得成功（870行）
[ ] RQ2: 01-setup.yml に Artifact 保存ステップがある
[ ] RQ2: 02-tools.yml に Artifact ダウンロード + フォールバックがある
```
