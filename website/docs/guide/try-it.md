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

**他の認証ソースを使う場合:**

```bash
# Anthropic API key (subscription 不要)
export ANTHROPIC_API_KEY=sk-ant-api-...

# あるいは OpenAI / Gemini / Ollama でも OK (multi-runtime)
export OPENAI_API_KEY=sk-...
export GEMINI_API_KEY=...
ollama serve   # self-hosted Ollama を別ターミナルで
```

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

- **Claude** → 既定。何も設定不要
- **Codex** → `OPENAI_API_KEY` を export してから select
- **Gemini** → `GEMINI_API_KEY` を export
- **Ollama** → self-hosted なら `OLLAMA_HOST=http://localhost:11434`、cloud なら + `OLLAMA_API_KEY`
- **Copilot** → `gh auth login` + Copilot 契約 (Chat のみ、audit 不可)

各 runtime の deep dive は [Multi-runtime バックエンド](../operations/multi-runtime.md)。

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

## ルート B: CLI のみで監査を回す (CI / スクリプト向け)

```bash
# 同じく clone + uv sync まで済んだ前提
export KEYWORDS="ethereum execution client"
export SPEC_URLS="https://ethereum.github.io/execution-specs/src/"

uv run python scripts/run_phase.py --target 04 --workers 4
```

出力は `outputs/` 配下。Resume は自動 (`<phase>_PARTIAL_*.json` から処理済 ID を読む) なので Ctrl-C で止めて再開しても続きから。

### Runtime を切替える

```bash
# 利用可能な runtime を確認
uv run python scripts/run_phase.py --list-runtimes

# OpenRouter 経由で audit
export API_RUNNER_API_KEY=sk-or-v1-...
uv run python scripts/run_phase.py --target 04 --runtime api --workers 4

# JSON 出力で CI / speca-cli から消費
uv run python scripts/run_phase.py --target 04 --runtime api --json | tee pipeline.ndjson
```

[Multi-runtime バックエンド](../operations/multi-runtime.md) も参照。

### 失敗時のリカバリ

```bash
# 失敗 phase だけ force re-run
uv run python scripts/run_phase.py --phase 03 --force --workers 4

# 特定 phase をスキップ (Phase 02c の MCP 依存を回避)
uv run python scripts/run_phase.py --phase 01a 01b 01e 03 04 --workers 4

# Cleanup dry-run で対象を確認してから force
uv run python scripts/run_phase.py --phase 03 --cleanup-dry-run
```

詳しくは [トラブルシューティング](../operations/troubleshooting.md)。

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
