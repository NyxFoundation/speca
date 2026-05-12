# SPECA Web UI 設計 (issue #54)

ローカル web client から SPECA フレームワーク全体を操作・閲覧するための UI 設計。

## 1. ゴールとスコープ

### 1.1 ゴール

`.github/workflows/full-audit.yml` の workflow_dispatch をローカル web UI で再現し、加えて
issue #54 が要求する Findings Browser を内包する。具体的な達成事項:

- Browser からフォーム入力 → audit run を起動 (Action の workflow_dispatch 相当)
- 走行中 phase の進捗 / コスト / ログ末尾をリアルタイム観測
- Phase 03/04 (将来 05) の finding を一覧 → 詳細でドリル
- 複数 run を切り替え可能 (`.speca/runs/<run-id>/` を一次 index に使う)
- claude.ai OAuth (Pro/Max subscription) でログインして API key 不要で動かせる

### 1.2 非ゴール (v0 〜 v2 時点)

- リアルタイム pipeline 進捗を speca-cli TUI と統合する: 共存とする
- Cloudflare Pages / 外部ホスティング: ローカル前提

### 1.3 将来スコープ (v5 以降に検討、本書では設計余地のみ確保)

- **認証 / 多ユーザ**: localhost binding のままだが、同マシンに複数監査人がアクセスする / リモート転送する将来に備えてユーザ識別の層を切れるようにしておく
- **コメント機能**: finding ごとにレビューコメントを残せる
- **finding の編集 / 承認ワークフロー**: read-only から進めて、verdict 変更や approve/reject を扱えるようにする
- **永続化レイヤ**: 上記を実現するには local SQLite (or JSON file DB) が要る。subprocess + ファイル設計の純度は保ちつつ、UI 由来の状態だけ DB に切り出す

## 2. 設計方針

### 2.1 CLI との疎結合

Web UI ⇄ SPECA 本体の境界は **subprocess + ファイルシステム** に限定する。
orchestrator パッケージは web UI から import しない。

| 通信内容 | 手段 | 安定契約 |
|---|---|---|
| Phase 起動 | `uv run python3 scripts/run_phase.py --phase XX` を spawn | `run_phase.py` の CLI |
| 入力受け渡し | env var (`KEYWORDS`, `SPEC_URLS`, ...) と `outputs/*.json` 配置 | Action の env var セット |
| 進捗観測 | `outputs/logs/*.jsonl` を file watch + tail | stream-json schema |
| 結果取得 | `outputs/*PARTIAL*.json` 読み込み | Pydantic schema (`schemas/*.schema.json`) |
| 中断 | プロセス kill | SIGTERM |

`run_phase.py` の CLI と `outputs/` JSON schema が壊れない限り、orchestrator 内部の
refactor は web UI に影響しない。

### 2.2 アーキテクチャ

```
[Browser SPA (React + TypeScript + Vite)]
   │  HTTP / WebSocket / SSE (127.0.0.1 のみ listen)
   ▼
[Backend (FastAPI, Python)]
   ├─ subprocess ──► scripts/run_phase.py          (Pipeline 操作)
   ├─ git plumbing ► audit/<target>/<run-id> branch
   ├─ filesystem ──► outputs/ , .speca/runs/<run-id>/
   └─ Anthropic SDK ► Claude API                   (Chat と tool use)
```

- backend は SPECA 同梱 (`web/server/` 等)、起動コマンド `uv run speca-web` 想定
- frontend は同 backend が静的配信 (build 成果物を FastAPI が serve)
- バイト送り合うのは JSON のみ、orchestrator 型は import しない
- chat 用の Claude API 呼び出しと、pipeline 用の subprocess 起動は **完全に別経路**。chat は SDK 直叩き (tool use 経由)、pipeline は `run_phase.py` 起動。同じ credentials を共有するが、コードパスは分離

## 3. 技術選定

| レイヤ | 選定 | 理由 |
|---|---|---|
| Backend 言語 | Python (FastAPI) | uv 環境既存、subprocess + ファイル監視で完結する |
| Frontend 言語 | TypeScript | 既存 cli/ (TypeScript) と揃う。schema 型を共有しやすい |
| Frontend フレームワーク | React 19 + Vite | Docusaurus 既存 (React 19) と揃う。Docusaurus 拡張ではなく独立 SPA とする (ローカル限定なので overkill) |
| ルーティング | React Router v6 | ファイルベースでなく宣言的にする (Next.js は overkill) |
| 状態管理 | TanStack Query + Zustand | サーバ状態は Query、UI 状態は Zustand |
| スタイリング | Nyx Foundation tokens (custom.css) + CSS Modules | 既存 `website/src/css/custom.css` の token (ミニマル B&W / WCAG 2.2 AA / システムフォント / 6-8px radius / 150-300ms motion) を web/ にも import。Tailwind や shadcn/ui は **入れない** — Docusaurus サイトとブランド一貫、bundle / 学習コスト最小、必要なら後で部分採用可能 |
| リアルタイム | WebSocket (stream-json) + SSE (chat ストリーミング) | 用途で使い分け |
| 検索 | Fuse.js (client-side fuzzy) | 静的 JSON を読むだけで動く |
| run index | `.speca/runs/<run-id>/manifest.json` (PR #55) | append-only 設計が web UI からの「読むだけ」と相性良い |
| Chat バックエンド | Anthropic SDK 直叩き (Python `anthropic` lib + tool use) | Claude Code CLI 経由は tool 定義が二重化する |
| 永続化 (将来) | SQLite (sqlite-utils or sqlmodel) | コメント・編集ログを v5 以降で持つ。orchestrator の outputs/ には触らず web UI 由来の状態のみ。chat 履歴は `~/.speca/web/conversations/<id>.json` に file ベースで持つ (DB は v5+ から) |
| 配布 | 同 repo `web/` 配下 | 別 repo に分けるほどの規模ではない |
| 既存 cli/ (TUI) | 共存・補完 | TUI は単一 phase 監視、Web は run 横断 |

## 4. UX フロー

### 4.1 初回起動

1. user: `uv run speca-web` → backend が `127.0.0.1:<port>` で listen、browser 自動起動
2. backend が `~/.claude/credentials.json` の有無を確認
3. 未ログインなら "**Claude にログイン**" 画面を表示

### 4.2 ログイン

1. "Claude にログイン" ボタン → backend が `claude login` を subprocess で spawn
2. CLI の標準フロー (browser で Anthropic 認可ページが開く) をそのまま流す
3. callback 完了後、`~/.claude/credentials.json` に保存される
4. web UI は `claude` CLI の出力を監視して "ログイン成功" を検出
5. 代替パス: 設定画面で `ANTHROPIC_API_KEY` 直接入力も可

credentials は raw 表示しない (`"logged in as <email>"` のみ)。

### 4.3 Run 起動

1. "**新規 run**" → フォーム表示。Action の workflow_dispatch inputs と同じ:
   - bug_bounty_url (required)
   - target_repo (required)
   - target_ref (optional)
   - contract_addresses (optional)
   - spec_urls (optional, auto-extract)
   - keywords (optional, auto-extract)
   - workers (default 4)
   - max_concurrent (default 64)
2. backend:
   1. `audit/<target_slug>/<YYYYMMDD-HHMMSS>` ブランチを切る
   2. `target_workspace/` に target repo を clone (or checkout 切替)
   3. Phase 0a (scope 抽出) → 0c (TARGET_INFO 作成) を順に subprocess 起動
   4. Phase 01a → 01b → 01e → 02c → 03 → 04 を逐次起動
   5. 各 phase 完了で `outputs/` を commit (push は opt-in)
3. UI:
   - 進行中 phase のバッチ完了数 / コスト累計 / ログ末尾 をリアルタイム表示
   - **中断** ボタン (SIGTERM)
   - **強制再実行** ボタン (`--force` フラグ付与で resume バイパス)

### 4.4 Run 一覧 / 切替

- `.speca/runs/` 配下を読んで run 一覧表示
- 各 run のサマリ: 開始時刻 / target / 進捗 phase / コスト / 完了 finding 数
- クリックで run 切替

### 4.5 Findings ブラウザ

issue #54 の核機能。以下を備える:

- **一覧**: severity / verdict / phase でフィルタ・ソート
- **詳細**: finding 本文 / Phase 04 3-gate 通過理由 / 引用コード / 関連 past-fix
- **横断検索**: severity / file / 関数名で fuzzy
- **Phase 05 critique** (issue #53 完了後): クエリ列 / ヒット URL / モデル判定差分

### 4.6 モバイル (360px 幅)

- 一覧テーブル → カードレイアウト
- 詳細画面は縦積み
- サイドバー → ハンバーガードロワー

### 4.7 Project Picker — 3 入口 → 1 フォーム

audit project (target repo / bug bounty) の選択は必須ステップ。初心者でも詰まらないよう、3 つの異なる入口が **1 つの確認フォーム** に合流する設計。

```
┌──────────────────────────────────────────────────────────┐
│  How to start an audit?                                  │
│                                                          │
│  ┌───────────┐  ┌───────────┐  ┌────────────────────┐    │
│  │ A. Saved  │  │ B. From   │  │ C. Ask Claude      │    │
│  │   targets │  │   URL     │  │   (chat)           │    │
│  └─────┬─────┘  └─────┬─────┘  └─────┬──────────────┘    │
│        └──────────────┴──────────────┘                   │
│                       ▼                                  │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Audit form (Action workflow_dispatch と同等)       │  │
│  │   bug_bounty_url / target_repo / target_ref ...   │  │
│  │   [Edit and review] → [Launch audit]              │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

| 入口 | 内容 | 実装コスト |
|---|---|---|
| **A. Saved targets** | 過去 audit した bug_bounty_url + target_repo を逆引きで `.speca/runs/*/manifest.json` から構築。1-click でフォーム pre-fill | tool 追加不要、`.speca/` を読むだけ |
| **B. From URL** | bug_bounty_url を貼ると、backend が `WebFetch` でメタ読み → scope / spec_urls / keywords を初期推定してフォームに pre-fill (Action `full-audit.yml` Step 0a の `claude --print` 処理を tool 化) | `WebFetch` tool 1 つ追加 |
| **C. Ask Claude (chat)** | "Immunefi の Uniswap V4 やりたい" のように自然言語で頼む → Claude が B の `WebFetch` tool を叩いて、提案値を埋めたフォームを user に提示 | chat 内 tool 1 個生やすだけ |

**重要原則**: どの入口から来ても、最後は user がフォームを確認してから launch。フォームが single source of truth で、UI の整合性が保たれる。

### 4.8 Chat UI — Dashboard との融合

Claude との対話 UI を dashboard に重ねる。chat は dashboard を置き換えるのではなく、dashboard の cross-cutting アシスタント (起動・停止・解説) として動く。

#### レイアウト

```
┌────────────────────────────────────────────────┬────────────┐
│  Dashboard (主領域)                            │  Chat ⌄    │
│   Tabs: Runs | Findings | Settings             │   msgs     │
│                                                │   ...      │
│                                                │   tool     │
│                                                │   card     │
│                                                │            │
│                                                │  [input]   │
└────────────────────────────────────────────────┴────────────┘
   ~70%                                              ~30%
```

- デスクトップ: 右サイド固定 panel (折りたたみ可)
- モバイル 360px: chat はデフォルト畳んだ FAB、開くと全画面オーバーレイ

#### Chat ↔ Dashboard の双方向バインド

| 方向 | 例 |
|---|---|
| Dashboard → Chat | run を dashboard で開く → chat に "context: run #abc (litecoin, Phase 04 中)" チップ表示 |
| Chat → Dashboard | Claude が `launch_pipeline` tool 実行 → dashboard の Runs 一覧に即追加 |
| 共通 | tool 結果カード (finding カード / run 進捗バー) は chat にもインライン埋め込み、dashboard でも同じデータを表示 (コンポーネント DRY) |

#### Tool セット (初期 5 + WebFetch)

| Tool | 用途 | 副作用 | 承認ゲート |
|---|---|---|---|
| `launch_pipeline` | 新規 audit 起動 | subprocess + git branch | 要承認 |
| `stop_pipeline` | 走行中 run の中断 (SIGTERM) | プロセス kill | 要承認 |
| `read_run_status` | run の現状取得 | 無 | 自動 |
| `list_findings` | filter で finding 一覧 | 無 | 自動 |
| `read_finding` | property_id 指定で詳細 | 無 | 自動 |
| `fetch_bounty_url` | bug_bounty_url を WebFetch して scope 推定 | 無 (外部 HTTP fetch のみ) | 自動 (URL のみ表示) |

副作用大の tool (`launch_*` / `stop_*`) は実行前に **承認カード** を chat に表示: `[Approve] [Edit and review] [Cancel]`。

#### Chat UX 詳細

| 項目 | 仕様 |
|---|---|
| ストリーミング | SSE で token-by-token + tool_use イベント |
| Tool card | dashboard と同じカードコンポーネントを chat にもインライン埋め込み |
| 履歴 | per-project 永続化 (`.speca/web/conversations/<id>.json`)、サイドバーから呼び戻し |
| 承認ゲート | "今回だけ" / "この会話中ずっと" / "毎回確認" の 3 段切替 |
| モデル切替 | Opus (思考) / Sonnet (tool 主体) / Haiku (要約) を chat 内で切替可能 |
| コスト表示 | 1 ターンごと `+$0.0234 (input 4.2k / output 1.1k)` を吹き出し下に表示 |
| 認証 | dashboard と同じ OAuth / API key を共有 |
| 多言語 | Claude のデフォルト挙動でユーザのメッセージ言語に追従 |

### 4.9 Run 可視化 — GitHub Actions 風

Run の進捗・履歴は GitHub Actions の workflow run UI の体験を踏襲する。SPECA の "phase" = GH Actions の "step"、"audit run" = "workflow run"。

#### Run List (= GH の workflow runs 一覧)

```
┌──────────────────────────────────────────────────────────┐
│  Runs                                       [+ New run]  │
│                                                          │
│  ✓ audit-litecoin-20260512-143000   uniswap-v4   2m 14s  │
│  • audit-uniswap-20260512-142100    target-x     running │
│  ✗ audit-failed-test                ...          43s     │
│  ↻ audit-2026-05-11                 ...          1h 22m  │
└──────────────────────────────────────────────────────────┘
```

- 状態アイコン: `✓` 成功 / `✗` 失敗 / `•` 走行中 (アニメ) / `↻` キャンセル / `⊘` skipped
- 1 行 = 1 run。target slug + 経過時間 / 進捗 / コスト
- ソート: 開始時刻 (新しい順) デフォルト、target / status / cost でも可
- フィルタ: status / target / 期間
- 配色: 状態アイコンのみ色付け (B&W ベースの中でアクセント色は最小限)

#### Run Detail (= GH の workflow run ページ)

```
┌──────────────────────────────────────────────────────────┐
│  audit-litecoin-20260512-143000                          │
│  target: litecoin-project/litecoin @ master              │
│  branch: audit/litecoin-project-litecoin/20260512-143000 │
│  started 2 min ago · cost $1.42 / $5.00                  │
│  [Stop] [Re-run failed phases] [Open in GitHub]          │
│  ─────────────────────────────────────────────           │
│  ✓ 0a Scope extraction                       12s         │
│  ✓ 0b Target checkout                        4s          │
│  ✓ 01a Spec discovery                        38s         │
│  ✓ 01b Subgraph extraction                   2m 4s       │
│  ✓ 01e Property generation                   1m 17s      │
│  ✓ 02c Code pre-resolution                   3m 22s      │
│  • 03 Audit Map                              4/12 batches│
│                                              ▶ Show logs │
│  ⊘ 04 Review (queued)                                    │
└──────────────────────────────────────────────────────────┘
```

- Phase 行クリックで展開、stream-json log を表示 (折り畳み可、自動スクロール)
- "Show logs" 横にはバッチ単位の進捗バー
- ヘッダにメタ情報固定 (target / cost / 経過時間)、scroll でもスティッキー
- "Re-run failed phases" は `--force` で該当 phase だけ再実行
- branch リンクで GitHub 上の audit branch を直接開く (push 済みの場合のみ表示)

#### Log View (= GH の step log)

- モノスペースフォント (token は既存 `--ifm-code-font-size`)
- ANSI カラー対応 (`ansi-to-html` 等)
- 検索: 行内テキスト、警告 / エラー行ハイライト
- 末尾固定: 走行中は自動スクロール、user スクロール時は止める
- "Download log" / "Copy log" ボタン
- log 量制限 (1 phase 数千行) に備え、UI 側で chunk render (react-window 等)

#### 配色

Nyx tokens (B&W 基調) に対し、状態色のみ最小限のアクセント:

- 成功 = `--ifm-color-primary` (黒 / 白) もしくは緑 `oklch(0.65 0.16 145)`
- 失敗 = 赤 `oklch(0.55 0.20 30)`
- 走行中 = 青 `oklch(0.65 0.13 240)` + pulse アニメ
- キャンセル / スキップ = グレー `oklch(0.55 0.005 258)`
- ライト/ダーク両モードで oklch chroma を保ち WCAG AA 維持

### 4.10.5 外部連携 (オプション)

#### Fork to GitHub

- 用途: finding を見つけたら user の GH アカウントに target_repo を fork して、fix PR の準備に入れる
- 配置: Run Detail のアクション列に `[Fork to GitHub]` ボタン
- 実装: backend が `gh repo fork <target_repo> --clone=false` を spawn、結果の fork_url を返す
- 承認ゲート: dry-run プレビュー (どこへ fork するか) → user 承認 → 実行
- 前提: `gh` CLI がインストール済み + `gh auth login` 済み。未設定なら設定画面に誘導 (強制しない)

#### Open in VSCode (多箇所配置)

`code` CLI が PATH に通っていれば、以下すべての箇所でワンクリックで開ける:

- **Run Detail ヘッダ**: `[VSCode で target を開く]` → `code <target_workspace_<run_id>>`
- **各 Phase 行**: `[VSCode で log を開く]` → `code <outputs/logs/<phase>_*.jsonl>`
- **Finding 詳細の引用箇所**: `file: src/net.cpp::L80-91` 行に `[VSCode で開く]` → `code -g <target_workspace>/src/net.cpp:80`
- **Findings 一覧の各行**: code_path セルが clickable、クリックで該当ファイル + 行を VSCode で開く
- **Run List の各行**: コンテキストメニュー (右クリック / `…`) から "VSCode で audit branch を開く" → `code <speca repo path>` (audit ブランチ checkout 済み状態)
- **Settings**: "VSCode で `.speca/` を開く" / "VSCode で `~/.claude/` を開く" 等のメンテ用エントリ

DRY のため `<OpenInVSCode>` という共通コンポーネントを 1 つ用意し、すべての場所で再利用:

```tsx
<OpenInVSCode path={absPath} line={lineNumber?} label="VSCode で開く" />
```

副作用: なし (`code` プロセス起動のみ、外部書き込みは行わない)。前提 CLI 未設定なら disabled 表示にして tooltip で誘導。

### 4.10 初心者フレンドリー原則

設計全体に共通する UX 原則。実装時に「これ初心者わかる?」のチェックリスト:

1. **空状態に "次の一歩" を必ず表示** — Runs が空 → "新規 audit を始める" ボタンと "サンプルプロジェクトで試す" リンク
2. **専門用語にツールチップ** — CWE / STRIDE / property / subgraph 等、用語の隣に `?` でホバー解説
3. **デフォルト値を必ず提示** — workers=4 / max_concurrent=64 / max_budget_usd=5.00 等、空欄を作らない
4. **エラーメッセージは "何をすればよいか" まで書く** — "URL invalid" だけで終わらず "Immunefi / Sherlock / Code4rena の bug bounty ページ URL を貼ってください" まで
5. **副作用前に必ず確認ダイアログ** — pipeline 起動 / 停止 / 強制再実行 は確認 step を挟む
6. **初回起動時のガイドツアー** — login → first run までを 3 ステップで案内 (skip 可、再表示も可)
7. **デモプロジェクトを 1 つ pre-install** — `litecoin-project/litecoin` 程度の小さめ target を Saved targets に最初から入れて、空状態を回避
8. **進捗には常に ETA / 残量** — "Phase 03 走行中" だけでなく "Phase 03 (4/12 batches, ~3 分残)"
9. **コスト upfront 表示** — run 起動フォームで "推定コスト: $X (max budget $5.00)" を出してから launch
10. **やり直し / リカバリ経路を必ず用意** — 失敗 phase は "Re-run failed" で 1-click 復帰、cancel した run は履歴に残して `--force` で再開可能

## 5. 認証

| 認証方式 | 用途 | 実装 |
|---|---|---|
| OAuth (claude.ai Pro/Max) ★ デフォルト | subscription quota で動かす | `claude login` を subprocess で呼ぶ。credentials は `~/.claude/credentials.json` に直保存 |
| API key | API 課金プラン | 設定画面で `ANTHROPIC_API_KEY` 入力、env var として subprocess に渡す |

- 両方設定済みなら OAuth 優先 (claude-code CLI のデフォルト挙動)
- credentials は web UI で raw 表示しない (`logged in as <email>` のみ)
- 127.0.0.1 binding なので他デバイスからの盗難はネットワーク層で防ぐ
- token refresh は claude-code CLI が自前でやってる前提 (web UI 側は触らない)

## 6. Run ライフサイクル

### 6.1 二重構造

PR #55 の archive substrate と git branch は役割が異なるので両方走らせる:

| 媒体 | 用途 | 形式 |
|---|---|---|
| `.speca/runs/<run-id>/` | ローカルトレース・分析。manifest / prompt sha / env snapshot / cost.json | append-only ファイル群 |
| `audit/<target>/<run-id>` git branch | 監査成果物の versioned snapshot、共有用 | git history |

### 6.2 git 運用

- branch 命名: `audit/<target_repo_slug>/<YYYYMMDD-HHMMSS>` (Action 踏襲)
- commit author: ユーザの git config をそのまま使う (Action の Security Agent Bot は使わない)
- commit message: Phase 完了ごとに `"01a: discovery complete"` 等 (Action 踏襲)
- push remote: **デフォルト無効**、UI で remote URL 設定すれば自動 push 有効化
- failed phase: 途中エラーでも `outputs/` は commit (Action の `if: success() || failure()` 相当)

### 6.3 outputs 配置

- 1 マシンで同時に複数 audit を走らせるケースを想定する
- 単一 `outputs/` を共有すると衝突するため、各 run は `outputs/<run_id>/` 配下にネスト
- `run_phase.py` の出力先制御は `SPECA_OUTPUT_DIR` env var で行う (既存メカニズム)

### 6.4 target_workspace の管理

- backend が `git clone <target_repo> --branch <ref> target_workspace_<run_id>/` する
- 同時走行時の干渉回避のため run_id サフィックスを付ける
- run 終了後はキャッシュとして残す (再 audit 時にクローン省略可)

### 6.5 Resume

- 既存 `ResumeManager` (PARTIAL から既処理 ID 拾う) はそのまま活用
- UI 側で "再開" / "強制やり直し (`--force`)" を切替可
- 走行中の phase を kill して再開した場合、PARTIAL は残るので次回起動時に skip される

### 6.6 コスト可視化

- 走行中: PR #55 の `phases/<phase>/cost.json` を WebSocket で push
- 累計: manifest.json の `cost_usd_total` を一覧画面に表示
- budget 残量バーは UI 上でも `max_budget_usd` から計算

## 7. データ契約

### 7.1 Backend ↔ Frontend (HTTP)

| Endpoint | Method | Body | Response |
|---|---|---|---|
| `/runs` | POST | form inputs (Section 4.3) | `{ run_id }` |
| `/runs` | GET | - | run の配列 (`.speca/runs/` から構築) |
| `/runs/<id>` | GET | - | manifest + 現在 phase の進捗 |
| `/runs/<id>/findings` | GET | `?phase=04&severity=High` 等 | finding の配列 |
| `/runs/<id>/findings/<property_id>` | GET | - | finding 詳細 + 引用コード |
| `/runs/<id>/cancel` | POST | - | SIGTERM 発行 |
| `/runs/<id>/rerun` | POST | `{ phases: ["03","04"] }` | `--force` で該当 phase 再実行 |
| `/auth/login` | POST | - | OAuth 開始、`claude login` を spawn |
| `/auth/api-key` | POST | `{ key }` | API key を `~/.claude/credentials.json` に書く |
| `/auth/status` | GET | - | `{ logged_in: bool, method: "oauth"\|"api_key" }` |
| `/picker/saved` | GET | - | Saved targets (`.speca/runs/*/manifest.json` から逆引き) |
| `/picker/fetch_url` | POST | `{ bug_bounty_url }` | WebFetch で scope / spec_urls / keywords を推定 |
| `/chat/conversations` | GET | - | per-project chat 履歴一覧 |
| `/chat/conversations/<id>` | GET | - | 1 conversation の全 message |
| `/chat/conversations/<id>/messages` | POST | `{ text }` | user message を append、SSE で response stream |
| `/chat/tool_approve` | POST | `{ tool_call_id, action: "approve"\|"edit"\|"cancel" }` | 副作用 tool の承認応答 |
| `/integrations/fork` | POST | `{ target_repo, into_owner? }` | `gh repo fork` spawn、`{ fork_url }` |
| `/integrations/open-in-vscode` | POST | `{ path, line? }` | `code` (or `code -g <path>:<line>`) spawn |
| `/integrations/status` | GET | - | `{ gh: { installed, authed }, code: { installed } }` |

### 7.2 Backend ↔ Frontend (WebSocket / SSE)

#### WebSocket `/ws/runs/<id>/stream` — pipeline 進捗

- phase 進捗 / log line / cost 更新を push
  ```jsonc
  { "type": "phase_progress", "phase": "03", "completed": 24, "total": 50 }
  { "type": "log_line", "phase": "03", "line": "<stream-json line>" }
  { "type": "cost_update", "phase": "03", "snapshot": { ... } }
  { "type": "phase_complete", "phase": "03", "status": "ok" }
  ```

#### SSE `/chat/conversations/<id>/messages` — chat ストリーミング

- POST レスポンスを SSE で返す。Anthropic SDK の stream events をリレー:
  ```jsonc
  { "type": "content_block_delta", "delta": { "text": "..." } }
  { "type": "tool_use_start", "tool_call_id": "tu_abc", "name": "launch_pipeline", "input_partial": {} }
  { "type": "tool_approval_required", "tool_call_id": "tu_abc", "preview": { ... } }
  { "type": "tool_use_result", "tool_call_id": "tu_abc", "result": { ... } }
  { "type": "message_stop", "usage": { "input_tokens": 4200, "output_tokens": 1100 } }
  ```

### 7.3 Backend ↔ subprocess

- env var: `KEYWORDS`, `SPEC_URLS`, `SPECA_OUTPUT_DIR`, `GITHUB_PERSONAL_ACCESS_TOKEN`, `ANTHROPIC_API_KEY`
- 起動コマンド: `uv run python3 scripts/run_phase.py --phase XX --workers N --max-concurrent M`
- stdout / stderr: backend が capture して WebSocket に流す

### 7.4 Finding 正規化スキーマ (frontend 内部)

```ts
type Finding = {
  run_id: string;
  phase: "03" | "04" | "05";
  property_id: string;
  severity: "Critical" | "High" | "Medium" | "Low" | "Informational";
  verdict?: "CONFIRMED_VULNERABILITY" | "CONFIRMED_POTENTIAL" |
            "DISPUTED_FP" | "DOWNGRADED" | "NEEDS_MANUAL_REVIEW" | "PASS_THROUGH";
  file?: string;       // src/net.cpp
  line_range?: string; // L80-91
  evidence_snippet?: string;
  proof_trace?: string;
  gates_passed?: string[];   // Phase 04 のみ
  reviewer_notes?: string;
  related_past_fixes?: string[]; // 将来 dataset 連携
  critique?: CritiqueTrace;      // Phase 05 (将来)
};
```

正規化ロジックは frontend 側に書く (backend は raw を返すだけ、疎結合を保つ)。

## 8. 段階リリース

### 8.1 v0 — Findings 表示 + 基本骨組み

- Nyx tokens (custom.css) を web/ にも導入してブランド統一
- ログイン (OAuth + API key 両方)
- `.speca/runs/` 一覧 / 切替 (GitHub Actions 風 run list)
- 単一 run の Phase 03 / 04 finding 一覧
- 詳細画面 (基本)
- 空状態 / 用語ツールチップ / デモプロジェクト pre-install (Section 4.10 初心者原則)
- run 起動・監視は **未対応** (read のみ)
- chat は **読むだけ** (`read_*` tool のみ解放、`launch_*` / `stop_*` は v1 から)

これだけで issue #54 の Findings Browser 部分の最小要件は満たせる。

### 8.2 v1 — Run 起動・監視 + GH Actions 風 Run Detail

- 新規 run フォーム (Action workflow_dispatch 同等)
- Project Picker (A. Saved / B. From URL / C. Chat の 3 入口)
- `WebFetch` tool 追加 (bug_bounty_url → scope 推定)
- subprocess spawn + `audit/<target>/<run-id>` ブランチ作成
- WebSocket で phase 進捗 / コスト / ログ tail
- GH Actions 風 Run Detail (phase = step として展開・log 表示)
- 中断 (SIGTERM) / 強制再実行 (`--force`)
- Chat tool に `launch_pipeline` / `stop_pipeline` 追加 (承認ゲート付き)

### 8.3 v2 — Multi-run / target_workspace 管理

- 同時走行
- target repo の自動 clone / cache
- 複数 run の比較 (同 target で実行した別タイミングの diff)

### 8.4 v3 — Phase 05 critique 対応 (issue #53 完了後)

- critique トレース表示
- クエリ → ヒット URL → モデル判定差分

### 8.5 v4 — 検索 / past-fix 連携

- Fuse.js 全文検索
- HF `vulnerability-reports/ethereum/` から類似 past-fix 引っ張る

### 8.6 v5 — 認証 / 多ユーザ (issue #54 で当初 non-goal だった項目)

- backend に local user テーブル (SQLite) を追加
- ログイン session は token cookie + httpOnly
- 各 run / コメントに `created_by` を持たせる
- 既存 localhost 単独利用との互換性は維持 (single-user モードがデフォルト)
- リモート転送 (SSH トンネル等) で複数監査人が同 backend を共有するシナリオを想定

### 8.7 v6 — コメント / 編集 / 承認ワークフロー

- finding に対するレビューコメント (markdown 対応)
- verdict の手動上書き (Phase 04 の自動判定を監査人が override)
- approve / reject / re-audit リクエストの状態遷移
- 全変更を audit log に残す (誰がいつ何を変えたか追跡可能)
- 永続化先: `~/.speca/web.db` (SQLite)。orchestrator 側 outputs/ には触らない

### 8.8 スコープ境界の維持

v5 / v6 を追加しても、CLI との疎結合 (Section 2.1) は変えない:

- web UI 由来の状態 (ユーザ / コメント / 編集) は **すべて web UI の DB に閉じる**
- orchestrator の `outputs/` / `.speca/runs/` には書き込まない
- subprocess 経由の audit 起動契約 (env var + 標準入力) は不変
- => CLI 側を将来書き換えても、web UI の付加機能は影響を受けない

## 9. オープン課題

設計確定後に詰める / 実装時に判断するもの:

- **finding の引用コード表示**: target_workspace を backend が serve するか、frontend が file:// で読むか
- **stream-json の集約**: 1 phase で 数千行出るログをそのまま push するとブラウザが重い → 要約 / サンプリング戦略
- **multi-run の同時走行リソース制限**: workers / max_concurrent の合算が CPU・API レート上限を超えないようガード
- **port 衝突**: 127.0.0.1 の listen port、デフォルト固定 (e.g. 7411) vs auto-pick
- **既ログインの検出**: `claude whoami` 等が claude-code CLI から取れるか要確認
- **Chat ↔ Pipeline の credentials 同居**: OAuth で chat 用の Anthropic SDK 呼び出しと pipeline 用の `claude` CLI 呼び出しが同じ credentials を共有する設計。SDK が OAuth トークンを直接読めるか / API key にフォールバックすべきかは実装時に検証
- **Tool 承認の UX 粒度**: "今回だけ承認 / この会話中ずっと承認 / 毎回確認" の状態管理。会話を再開した時に "ずっと承認" は引き継ぐべきか
- **Chat 履歴の検索**: 過去 conversation 数百件溜まった時に Fuse.js で検索可能にするか
- **Run Detail の log 量**: 1 phase 数千行を chunk render (react-window) で捌くとして、検索・スクロール位置同期のパフォーマンス
- **状態色 (oklch) の dark mode 検証**: 緑 / 赤 / 青のアクセント色が暗背景でも WCAG AA を維持するか、調整 token を別途用意

## 10. 関連 issue / PR

- issue #54 (本設計の出発点) — Web GUI for browsing SPECA findings + Phase 05 critique traces
- issue #53 — Phase 05 critique 実装 (v3 で対応するデータソース)
- PR #55 — Archive substrate (`.speca/runs/<run-id>/`)、本設計の run index として活用
- PR #52 — Phase B 設計、eval harness の集計を将来 UI に出す余地
- Action `full-audit.yml` — 本 UI の挙動の reference / 仕様契約
