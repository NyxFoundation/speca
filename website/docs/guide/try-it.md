---
sidebar_position: 3
---

# とりあえず動かしてみる

CLI / Web UI / multi-runtime の **3 ルート** で試せます。**Web UI が一番簡単**なので初めての方はそこから。各ステップに「ここで失敗したらこう直す」も併記しています。

## 前提

| 項目 | 必要 |
|---|---|
| Node.js | ≥ 20 |
| Python | 3.12 (`uv` 推奨) |
| git | 任意のバージョン |
| OS | Windows 11 / macOS 14 / Ubuntu 22.04 検証済 |
| 認証 | 下のいずれか 1 つ: claude.ai サブスク (Pro/Max) / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` / Ollama (self-hosted は無料) |

事前確認:

```bash
node --version    # v20.x 以上
uv --version      # 0.6 以上
git --version     # 任意
```

---

## ルート A: Web UI で監査を回す (初心者向け)

### 1. clone + 依存解決

```bash
git clone https://github.com/NyxFoundation/speca.git
cd speca

uv sync                          # Python 依存をインストール
cd web/frontend && npm install   # Frontend 依存
cd ../..
```

**失敗したら:**
- `uv sync` がエラー → `python -V` で 3.12 を確認、PATH 上に `python` が無い場合は `uv python install 3.12`
- `npm install` がエラー → `node -v` が v20 未満なら `nvm install 20 && nvm use 20`
- Windows で `cd web/frontend && npm install` の sh 構文がダメ → PowerShell では `cd web\frontend; npm install; cd ..\..`

### 2. claude にログイン (推奨経路)

```bash
npm install -g @anthropic-ai/claude-code
claude auth login        # ブラウザが開いて claude.ai OAuth
```

**確認:**

```bash
claude auth status --json
# → { "loggedIn": true, "authMethod": "claude.ai", "email": "...", "subscriptionType": "max" }
```

**他の認証ソースを使う場合 (API key / OAuth 両対応):**

```bash
# --- Anthropic ---
# OAuth (Pro/Max subscription)
claude auth login
# あるいは API key
export ANTHROPIC_API_KEY=sk-ant-api-...

# --- OpenAI Codex ---
# OAuth (ChatGPT plan)
npm install -g @openai/codex
codex login
# あるいは API key
printenv OPENAI_API_KEY | codex login --with-api-key
# あるいは env var で直接 (audit pipeline 向け)
export OPENAI_API_KEY=sk-...

# --- Google Gemini ---
# API key (シンプル)
export GEMINI_API_KEY=...                     # https://aistudio.google.com/apikey
# あるいは Google OAuth (Application Default Credentials)
gcloud auth application-default login
export GOOGLE_GENAI_USE_GCA=true

# --- Ollama (OAuth 無し) ---
# Self-hosted (認証不要)
ollama serve   # 別ターミナルで
export OLLAMA_HOST=http://localhost:11434
# Cloud (API key)
export OLLAMA_HOST=https://ollama.com
export OLLAMA_API_KEY=...

# --- GitHub Copilot (chat のみ、audit 非対応) ---
gh auth login                                  # GitHub OAuth
gh extension install github/gh-copilot
```

:::tip OAuth と API key の使い分け
- **OAuth** は subscription 課金 (Pro/Max plan / ChatGPT plan / Google personal account) に乗ります。トークン管理を CLI が代行するので楽。
- **API key** は従量課金。CI / 自動化に向きます。
- どちらが利用可能かは `/diagnostics` ページや `--list-runtimes` で確認できます。
:::

### 3. Web サーバ起動

```bash
uv run speca-web --port 7411 --host 127.0.0.1 --serve-frontend
```

期待ログ:

```
INFO:     Started server process [...]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:7411
```

ブラウザで http://127.0.0.1:7411/ を開く:

![Dashboard](/img/web-ui/01_dashboard_default.png)

**失敗したら:**
- ポート競合 → `--port 8000` 等に変更
- `claude auth status` は通るが Web UI で `logged_in: false` → 認証パスのバグ。`ls ~/.claude/.credentials.json` (先頭ドット注意) で実ファイルがあるか確認
- ブラウザが繋がらない → ファイアウォール。`--host 0.0.0.0` で公開、または `127.0.0.1` でループバック確認

### 4. (オプション) Runtime を切替えてみる

`/settings` を開き **Chat runtime** セクションで claude 以外を選んでみます:

![Runtime selector](/img/web-ui/11_runtime_selector.png)

| Runtime | OAuth | API key | サーバが必要な env / 認証 |
|---|---|---|---|
| **Claude** | `claude auth login` | `ANTHROPIC_API_KEY` | 既定 — 何も設定不要 |
| **Codex** | `codex login` | `OPENAI_API_KEY` | 認証済の CLI がある or `OPENAI_API_KEY` を export |
| **Gemini** | `gcloud auth application-default login` + `GOOGLE_GENAI_USE_GCA=true` | `GEMINI_API_KEY` | いずれかを export |
| **Ollama** | — (OAuth 無し) | cloud は `OLLAMA_API_KEY`、self-hosted は不要 | `OLLAMA_HOST` を必要に応じて (デフォルト cloud) |
| **Copilot** | `gh auth login` (GitHub OAuth) | — (Copilot 契約必須) | Chat のみ、audit 不可 |

availability bagde `✓` / `!` は「サーバ環境変数 / CLI の状態」を見ます。env を export してから Web サーバ再起動が確実です。各 runtime の deep dive は [Multi-runtime バックエンド](../operations/multi-runtime.md)。

### 5. 監査 run を開始

ダッシュボードの「+ 新規 run」 → **Picker** か **Wizard** で対象リポジトリ情報を入力。

**初心者向け: Wizard モード** (`/runs/new/wizard`)

1. **プロジェクト種別** — `smart_contract` / `web_app` / `library` / `other`
2. **対象リポジトリ** — `owner/name` (例: `OpenZeppelin/openzeppelin-contracts`)
3. **対象 ref** — 空欄でデフォルトブランチ、または `v5.0.0` 等
4. **スコープ** — Bug bounty URL があれば貼る、無ければ空
5. **Spec URLs** — オプション (Phase 01a の seed)
6. **確認** — Launch

**失敗パターン:**

| エラー | 意味 | 修正方法 |
|---|---|---|
| `clone_failed` | private repo / typo / network | `git ls-remote https://github.com/<owner>/<name>` で疎通確認。private なら `GH_TOKEN` env を export してから再起動 |
| `invalid_target_repo` | スラグ形式不正 | `owner/name` のシンプル形式に直す。`https://` プレフィックス不要 |
| `ref_not_found` | branch/tag が origin に無い | `git ls-remote --tags --heads <repo>` で実在チェック |
| `worktree_failed` | `.speca/workspaces/` の汚染 | `rm -rf .speca/workspaces/<target>` で再生成させる |
| `anthropic_unreachable` | API 障害 or auth 切れ | `claude auth status --json` 再確認、status.anthropic.com を見る |

エラーは画面上のモーダルで日本語の対処付きで出ます (CLI spec §10.4 の 7 ケース対応)。

### 6. Run 進捗を眺める

![Run detail with phases](/img/web-ui/05_run_detail_budget_phases.png)

各 phase をクリックして展開、または phase 行を Tab focus して `l` キーでログペインを開く。`f` で個別 phase の force re-run。

**予算超過:** ゲージをクリックして cap-bump:

![Cap-bump modal](/img/web-ui/06_budget_cap_bump_modal.png)

### 7. Findings 閲覧

![Findings list](/img/web-ui/03_findings_list.png)

DSL でフィルタ:

```
severity:HIGH|CRITICAL verdict:CONFIRMED_VULNERABILITY path:contracts/**/*.sol
```

`?glob=` URL param でも directly link 可:

```
http://127.0.0.1:7411/runs/<id>/findings?glob=contracts/**/*.sol
```

行クリックで詳細 (Prism コードハイライト):

![Finding detail](/img/web-ui/04_finding_detail_code_highlight.png)

「Ask Claude about this finding」で chat に finding を inject。

### 8. (オプション) Markdown export

Findings 一覧の **Export Markdown** で severity 別レポートを 1 ファイルダウンロード。バグ報告 / レビュー資料の下書きになります。

---

## ルート B: CLI で監査を回す (CI / スクリプト向け / 細かい制御がしたい人)

Web UI が立ち上げず純粋に CLI で完結したい / GitHub Actions に組み込みたい場合のルート。Route A と同じ環境 (clone + `uv sync`) を共有します。

### B-1. プリフライト

```bash
# Python / Node / git / claude CLI / MCP server がそろっているか
uv run python -c "import sys; print(sys.version)"
node --version
which claude    # or where claude (Windows)
bash scripts/setup_mcp.sh --verify
```

`--verify` で MCP server が登録済か確認できます。未登録なら `bash scripts/setup_mcp.sh` (無印) で再登録。

### B-2. ターゲット情報を書く

CLI からは `outputs/TARGET_INFO.json` と `outputs/BUG_BOUNTY_SCOPE.json` を**手書き**するのが一番素直です (Wizard 相当を直接書くだけ):

```bash
mkdir -p outputs
```

```json title="outputs/TARGET_INFO.json"
{
  "repository": "OpenZeppelin/openzeppelin-contracts",
  "ref": "v5.0.0",
  "project_type": "smart_contract"
}
```

```json title="outputs/BUG_BOUNTY_SCOPE.json"
{
  "url": "https://www.immunefi.com/bounty/openzeppelin",
  "scope_summary": "Core ERC-20/721 + access control contracts",
  "in_scope_assets": [
    "contracts/access/Ownable.sol",
    "contracts/access/AccessControl.sol",
    "contracts/token/ERC20/**/*.sol"
  ],
  "spec_urls": [
    "https://docs.openzeppelin.com/contracts/5.x/access-control"
  ]
}
```

スキーマの全フィールドは [設定ファイル](../getting-started/config-files.md) を参照。**ファイルが無いと Phase 01a が "Empty results" で止まります** ([トラブルシューティング C](../operations/troubleshooting.md))。

### B-3. (オプション) Phase 01a の env を上書き

`spec_urls` を `BUG_BOUNTY_SCOPE.json` に書かない場合は env から渡せます:

```bash
export KEYWORDS="ethereum execution client EIP"
export SPEC_URLS="https://ethereum.github.io/execution-specs/src/,https://geth.ethereum.org/docs"
```

両方未設定の場合、Phase 01a は default の Ethereum seed (KEYWORDS / SPEC_URLS の組み込み定数) を使います。

### B-4. パイプライン実行

#### パターン 1: 全フェーズを一気に

```bash
uv run python scripts/run_phase.py --target 04 --workers 4
```

`--target 04` は依存解決をして `01a → 01b → 01e → 02c → 03 → 04` の順に走らせます。

#### パターン 2: 1 フェーズずつ手動で

各フェーズの出力を確認しながら進める場合:

```bash
uv run python scripts/run_phase.py --phase 01a --workers 4
# → outputs/01a_STATE.json + outputs/01a_PARTIAL_*.json
cat outputs/01a_STATE.json | python -m json.tool | head -30

uv run python scripts/run_phase.py --phase 01b --workers 4
# → outputs/01b_PARTIAL_*.json + outputs/graphs/

uv run python scripts/run_phase.py --phase 01e --workers 4
uv run python scripts/run_phase.py --phase 02c --workers 4
uv run python scripts/run_phase.py --phase 03 --workers 4
uv run python scripts/run_phase.py --phase 04 --workers 4
```

#### パターン 3: 特定フェーズをスキップ

Phase 02c (MCP tree-sitter 依存) を runtime の都合でスキップしたいとき:

```bash
uv run python scripts/run_phase.py --phase 01a 01b 01e 03 04 --workers 4
```

#### よく使うフラグ

```bash
--force                    # resume 状態を無視して再実行
--workers 4                # 並列ワーカー数
--max-concurrent 8         # phase 内の同時 claude 起動数
--budget 50                # コスト上限 (USD)、超えたら exit 64
--output-dir outputs-test  # 別ディレクトリに出す (並列実行に便利)
--cleanup-dry-run          # 何が再実行対象か確認だけ
--json                     # NDJSON 出力 (CI 向け)
--no-tui                   # plain text (--json と併用可)
--01a-scope primary        # Phase 01a の状態を絞る (PR #65)
--runtime <name>           # runtime 切替 (PR #64)
--list-runtimes            # 利用可能な runtime を一覧表示
```

### B-5. Runtime を切替える

```bash
# 利用可能な runtime を確認
uv run python scripts/run_phase.py --list-runtimes
```

```text
Active runtime: claude
[OK] claude       Anthropic claude CLI (stream-json). ...
[..] api          OpenRouter-style HTTP. - Set API_RUNNER_API_KEY ...
[..] codex        OpenAI Chat API. - Set OPENAI_API_KEY ...
[..] gemini       Google Gemini (OpenAI-compat endpoint). - Set GEMINI_API_KEY ...
[..] ollama       Ollama (/v1/chat/completions). ...
[OK] copilot (stub) GitHub Copilot agentic CLI. Web chat works today; orchestrator runner is a follow-up.
```

JSON で吐かせる場合 (CI / `speca-cli` 用):

```bash
uv run python scripts/run_phase.py --list-runtimes --json | python -m json.tool
```

#### 各 runtime での実行例

```bash
# --- Claude (既定) — 何もしなくても claude が選ばれる
uv run python scripts/run_phase.py --target 04 --workers 4

# --- OpenRouter (汎用 OpenAI 互換) ---
export API_RUNNER_API_KEY=sk-or-v1-...
export API_RUNNER_BASE_URL=https://openrouter.ai/api/v1
export API_RUNNER_MODEL=deepseek/deepseek-r1
uv run python scripts/run_phase.py --target 04 --runtime api --workers 4

# --- OpenAI Codex ---
# OAuth 経由 (ChatGPT plan)
codex login
# あるいは API key
export OPENAI_API_KEY=sk-...
uv run python scripts/run_phase.py --target 04 --runtime codex --workers 4
# モデル上書き
export OPENAI_MODEL=gpt-4-turbo
uv run python scripts/run_phase.py --target 04 --runtime codex

# --- Google Gemini ---
# API key
export GEMINI_API_KEY=...
# あるいは Google OAuth (ADC)
gcloud auth application-default login
export GOOGLE_GENAI_USE_GCA=true
uv run python scripts/run_phase.py --target 04 --runtime gemini

# --- Ollama self-hosted ---
# ターミナル A
ollama serve
ollama pull llama3.2
# ターミナル B
export OLLAMA_HOST=http://localhost:11434
uv run python scripts/run_phase.py --target 04 --runtime ollama --workers 2

# --- Ollama cloud ---
export OLLAMA_HOST=https://ollama.com
export OLLAMA_API_KEY=...
uv run python scripts/run_phase.py --target 04 --runtime ollama
```

各 runtime の認証 / env 詳細は [Multi-runtime バックエンド](../operations/multi-runtime.md) に整理してあります。

### B-6. ログを眺める / 進捗を確認

TUI ダッシュボード (デフォルト) は phase 進捗とコストをリアルタイム表示します。別ターミナルで詳細ログを尾追いする場合:

```bash
# 最新フェーズのログを tail
tail -f outputs/logs/03_W0B0_*.jsonl | jq .

# PARTIAL の数 (進捗) を覗く
ls -1 outputs/03_PARTIAL_*.json | wc -l

# manifest を読む (中断したあと resume するときに役立つ)
cat .speca/runs/*/state.json | jq '{run_id, status, current_phase, cost_usd_total}'
```

### B-7. Findings を閲覧

#### 直接 ファイルを見る

```bash
# 全 finding を抽出
ls outputs/04_PARTIAL_*.json
cat outputs/04_PARTIAL_W0B0_*.json | jq '.findings[] | {property_id, severity, verdict, file}'

# 特定 severity だけ
cat outputs/04_PARTIAL_*.json | jq '.findings[] | select(.severity=="High")'
```

#### `speca browse` TUI を使う

```bash
speca browse                                    # ペルティ別の TUI ビューア
speca browse --severity Critical
speca browse --filter "verdict:CONFIRMED_*"
speca browse --filter "path:contracts/**/*.sol severity:HIGH"
```

`c` キーでコード抜粋、`f` でフィルタ編集、`q` で終了。DSL の全フォーマットは [CLI リファレンス](../getting-started/cli-reference.md#speca-browse) を参照。

#### Markdown export を CLI から

```bash
# 1 ファイルにまとめる
uv run python -c "
from pathlib import Path
import json
findings = []
for p in Path('outputs').glob('04_PARTIAL_*.json'):
    findings.extend(json.loads(p.read_text())['findings'])
findings.sort(key=lambda f: ('Critical High Medium Low Informational'.index(f['severity']), f['property_id']))
for f in findings:
    print(f'## {f[\"property_id\"]} — {f[\"severity\"]} / {f.get(\"verdict\", \"?\")}')
    if f.get('file'): print(f'`{f[\"file\"]}::{f.get(\"line_range\", \"\")}`')
    print()
    print(f.get('evidence_snippet', '_(no snippet)_'))
    print()
" > findings.md
```

### B-8. 個別 finding を Claude に質問

```bash
speca ask                                       # 最初の finding を選択
speca ask PROP-abc-001 --from outputs/04_PARTIAL_*.json
speca ask --severity High --filter "verdict:CONFIRMED_*"
```

その finding をコンテキストにした Claude Code セッションを開きます。Web UI の「Ask Claude about this finding」と同じ機能の CLI 版。

### B-9. 失敗時のリカバリ (手作業)

| 症状 | 確認 | 修復 |
|---|---|---|
| Phase 03 で circuit breaker (exit 65) | `tail -50 outputs/logs/03_*.jsonl \| jq .` | `--force --workers 2 --max-concurrent 4` で並列数を下げて再開 |
| 1 batch だけ破損 | 該当 `outputs/<phase>_PARTIAL_W<W>B<B>_*.json` を確認 | そのファイルだけ削除 → resume |
| 予算到達 (exit 64) | `cat .speca/runs/*/state.json \| jq .cost_usd_total` | `--budget 100` に上げる or scope を狭める |
| `BUG_BOUNTY_SCOPE.json missing` で sys.exit | `ls outputs/BUG_BOUNTY_SCOPE.json` | B-2 のテンプレで手書き作成 |
| `outputs/01a_STATE.json` が空 | `cat outputs/01a_STATE.json` | `SPEC_URLS` を export してから `--phase 01a --force` |
| Phase 02c で MCP 失敗 | `bash scripts/setup_mcp.sh --verify` | MCP 再登録 → `--phase 02c --force` |

```bash
# 失敗 phase だけ force re-run
uv run python scripts/run_phase.py --phase 03 --force --workers 4

# 1 batch だけ削除して resume
rm outputs/03_PARTIAL_W0B5_*.json
uv run python scripts/run_phase.py --phase 03

# 何が cleanup されるか dry-run で確認
uv run python scripts/run_phase.py --phase 03 --cleanup-dry-run
```

体系的な手作業修復は [トラブルシューティング](../operations/troubleshooting.md) に集約。

### B-10. CI に組み込む例 (GitHub Actions)

```yaml title=".github/workflows/audit.yml"
name: Nightly SPECA audit
on:
  schedule: [{ cron: "0 18 * * *" }]   # 03:00 JST 毎晩
  workflow_dispatch:

jobs:
  audit:
    runs-on: ubuntu-22.04
    timeout-minutes: 180
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - uses: astral-sh/setup-uv@v3
      - name: install claude CLI
        run: npm install -g @anthropic-ai/claude-code
      - name: install deps
        run: uv sync
      - name: target info
        run: |
          cat > outputs/TARGET_INFO.json <<EOF
          {"repository":"${{ github.repository }}","ref":"${{ github.sha }}","project_type":"smart_contract"}
          EOF
          cat > outputs/BUG_BOUNTY_SCOPE.json <<EOF
          {"in_scope_assets":["contracts/**/*.sol"],"spec_urls":[]}
          EOF
      - name: speca audit
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          uv run python scripts/run_phase.py \
            --target 04 \
            --workers 4 \
            --budget 50 \
            --json --no-tui > audit-events.ndjson
      - name: upload artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: speca-${{ github.run_id }}
          path: |
            outputs/
            audit-events.ndjson
            .speca/runs/
```

`--json` で吐いた NDJSON は `speca-cli` (issue #3) や JS の consumer から型付きで読めます。

### B-11. 並列で別の audit を走らせる

```bash
# ターミナル A
export SPECA_OUTPUT_DIR=outputs-target1
mkdir -p $SPECA_OUTPUT_DIR
# (target1 用の TARGET_INFO.json / BUG_BOUNTY_SCOPE.json を配置)
uv run python scripts/run_phase.py --target 04 --output-dir $SPECA_OUTPUT_DIR

# ターミナル B
export SPECA_OUTPUT_DIR=outputs-target2
# (...同様)
uv run python scripts/run_phase.py --target 04 --output-dir $SPECA_OUTPUT_DIR
```

`SPECA_OUTPUT_DIR` (環境変数) と `--output-dir` (フラグ) は同じ役割。Claude CLI の subscription 並列上限に注意してください ([トラブルシューティング B](../operations/troubleshooting.md))。

---

## ダッシュボード見方 (CLI TUI)

```
SPECA · openzeppelin-ownable-walkthrough          cost: $1.42 / $50 budget
─────────────────────────────────────────────────────────────────────────
01a Spec Discovery     ████████████████████  done   23 sections   $0.18
01b Subgraph Extract   ████████████████████  done   12 subgraphs  $0.24
01e Property Gen       ████████████████████  done   18 props      $0.31
02c Code Resolution    ████████░░░░░░░░░░░░  3 / 18 workers=4    $0.21
03 Audit Map           ░░░░░░░░░░░░░░░░░░░░  pending             —
04 Review              ░░░░░░░░░░░░░░░░░░░░  pending             —
```

各 phase の意味 → [パイプライン概要](../pipeline/overview.md)。

---

## コストと所要時間の目安

| コードベース | 実時間 | コスト (Sonnet 4.5) |
|---|---|---|
| 小型コントラクト (~1K LoC) | 5〜10 分 | $1〜5 |
| 中規模リポジトリ (~50K LoC) | 15〜40 分 | $20〜50 |
| 本番クライアント (~500K LoC) | 1〜3 時間 | $50〜100 |

| Runtime | 相対コスト | 速度 | 精度 (audit 用途) |
|---|---|---|---|
| Claude (Sonnet 4.5) | baseline | baseline | ★★★ |
| Claude Pro/Max OAuth | 課金なし (subscription) | baseline | ★★★ |
| Codex (GPT-4o) | ≈0.5x | baseline | ★★☆ |
| Gemini (2.0 Flash) | ≈0.3x | ★1.5x速 | ★★☆ |
| Ollama (self-hosted llama3.2:70b) | 0 (ローカル) | ★0.3x遅 | ★☆☆ |

コスト管理の詳細は [モデル選定の設計ノート](../design-notes/model-benchmark-takeaways.md)。

---

## クイックトラブルシューティング

詳細は **[トラブルシューティング](../operations/troubleshooting.md)** ページに集約しましたが、ここでは「とりあえずこれ試して」だけ列挙:

### Phase 01a で「Empty results」

`outputs/BUG_BOUNTY_SCOPE.json` が無いか `in_scope` が空。
**修正:** Wizard 再実行 or 手書きで `outputs/BUG_BOUNTY_SCOPE.json` を作成。フォーマットは [設定ファイル](../getting-started/config-files.md)。

### 終了コード 64 / 65 で停止

- **64** — `--budget` 到達 → 引き上げる or scope を狭める
- **65** — circuit breaker → `outputs/logs/<phase>_*.jsonl` で原因確認

### Chat パネルで応答が返ってこない

1. ヘッダの `signed in as ...` が出ているか
2. `/diagnostics` で claude / codex / gemini CLI の availability を確認
3. Settings で runtime を変えてみる (claude → ollama 等)

### Web UI が表示されない

```bash
curl http://127.0.0.1:7411/api/health
# → {"status":"ok"} なら API は生きている (frontend のキャッシュ問題)
```

ブラウザで Ctrl+Shift+R (hard reload) を試す。

---

## 初回監査が終わったあと

`speca browse` または `/runs/<id>/findings` を開くと findings リストが手元に来ています。次の質問はだいたいこうなります:

- **「どれが本物?」** — まず `--severity High --filter "verdict:CONFIRMED_*"`。verdict の意味は [3 ゲートレビュー](../concepts/gate-review.md)。
- **「なぜ X は dismiss された?」** — `DISPUTED_FP` は弾いたゲートを記録しています。`browse` の `Enter` で展開できます。
- **「証明のどのステップが失敗したのか?」** — `speca ask <property_id>` で finding のフルコンテキスト付きセッションを開きます。
- **「どこかで本物の仕様の文に遡れる?」** — はい、すべての finding が遡れます。連鎖は [ワークドエグザンプル](../concepts/worked-example.md) に図示されています。

---

## 次のステップ

- [CLI リファレンス](../getting-started/cli-reference.md) — 全フラグ + `--runtime` 切替
- [Web UI 機能](../operations/web-ui-features.md) — ブラウザ画面の全機能
- [Multi-runtime バックエンド](../operations/multi-runtime.md) — Codex / Gemini / Ollama / Copilot の使い方
- [トラブルシューティング](../operations/troubleshooting.md) — 失敗時の手作業リカバリ
- [パイプライン概要](../pipeline/overview.md) — 各フェーズの役割
- [概念 / Spec-driven](../concepts/spec-driven.md) — なぜこの設計が成立するか
