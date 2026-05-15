---
sidebar_position: 11
---

# Web UI の機能

`speca-web` のフロントエンドは、CLI spec ([issue #3](https://github.com/NyxFoundation/speca/issues/3)) の `speca-cli` をブラウザ上で再現することがゴールです。本ドキュメントは現在実装済みの主要機能を 1 ページに集約したものです。CLI spec のセクション番号も併記しているので、対応関係が分かるようにしてあります。

## ダッシュボード

`/runs` で過去の audit run の一覧。新規 run の起動 / フィルタリング / 再実行などができます。

![Dashboard default](/img/web-ui/01_dashboard_default.png)

## 認証

### Paste-code OAuth (CLI spec §4.5.1)

![Login screen with paste-code OAuth](/img/web-ui/10_login_paste_code.png)

ログイン画面の **Continue with claude.ai (paste-code)** ボタンを押すと、サーバが `claude auth login` をサブプロセスで起動し、stdout から認証 URL を抽出してブラウザの新タブで開きます。claude.ai 側で表示される verification code を Web UI のフォームに貼り付けると、サーバがそれをサブプロセスの stdin に流して `~/.claude/.credentials.json` を更新します。

旧フロー (OS のコンソール窓を開く方式) も Fallback として残してあります。

### API key 入力

サブスクリプションを持たないユーザは `ANTHROPIC_API_KEY` を直接入力できます。`~/.claude/credentials.json` (CLI が書き込む `.credentials.json` とは別) に保存します。

## Run 詳細

![Run detail with phase rows and budget gauge](/img/web-ui/05_run_detail_budget_phases.png)

### Phase 行のキーバインド (CLI spec §10.3)

Phase 行に focus 中:

| キー | 動作 |
| --- | --- |
| `Enter` / `Space` | 展開 |
| `l` | 展開 + ログペインへ scroll |
| `f` | 当該 phase だけ force re-run |
| `s` | skip (supervisor 側は未実装、ハンドラ呼び口だけ確保) |

### Budget gauge + cap-bump モーダル (CLI spec §5.3.3)

予算ゲージは `spent / cap` を 3 段階で着色 (~80% で黄、>=100% で赤)。ゲージをクリックすると **cap-bump モーダル** が開き、`max_budget_usd` を引き上げ / クリアできます:

![Budget cap-bump modal](/img/web-ui/06_budget_cap_bump_modal.png)

バックエンドは `POST /api/runs/<id>/budget_cap` で `state.json` に round-trip します。

## Findings

### 一覧 — Filter chip + DSL + Markdown export

![Findings list](/img/web-ui/03_findings_list.png)

severity / verdict / phase の chip で server side filter、追加の DSL 入力で client side のさらに細かい filter を AND 合成できます。`Export Markdown` ボタンで severity 別の Markdown 1 ファイル生成。

### Filter DSL (CLI spec §5.4.1)

検索ボックスで:

```
severity:HIGH|CRITICAL verdict:CONFIRMED_VULNERABILITY prop:PROP-6a4* path:src/**/*.sol token1 token2
```

- `severity:` / `verdict:` — OR-list 対応
- `prop:` / `repo:` — glob (`*` / `?`)
- `path:` — `**` で any-segment 対応 path glob
- 自由トークン — `property_id` / `file` / `proof_trace` / `evidence_snippet` / `reviewer_notes` を AND 検索

### `?glob=` URL param (CLI spec §3.5 `speca browse [glob]`)

```
/runs/<id>/findings?glob=contracts/**/*.sol
```

内部的に `?q=path:<glob>` に展開されるので、既存 DSL 入力との AND 合成も透過。

### Markdown export (CLI spec §3.1)

`Export Markdown` ボタンで severity 別バケットの Markdown を 1 ファイル生成。embedded backtick は dynamic fence で安全に出力、CRLF → LF 正規化済。

### コードハイライト (CLI spec §5.4.4 `[c]` keybinding)

![Finding detail with code highlight](/img/web-ui/04_finding_detail_code_highlight.png)

`FindingDetailPage` の evidence_snippet を Prism で highlight。Solidity / TS / JS / Python / Rust / Go / Java / C / C++ 同梱、未知言語はプレーンテキストにフォールバック。Solarized テーマも別パレットで対応。

## Chat パネル

![Chat panel](/img/web-ui/07_chat_panel_empty.png)

### Multi-runtime 切替 (CLI spec issue #3)

Chat パネルは 5 つのバックエンドに対応:

- `claude` (既定) — Anthropic Claude
- `codex` — OpenAI Codex (`codex exec --json`)
- `gemini` — Google Gemini (`gemini -p --output-format stream-json`)
- `ollama` — Ollama (HTTP `/api/chat`, cloud or self-hosted)
- `copilot` — GitHub Copilot (`gh copilot suggest`, 単発)

Settings ページから即座に切替可能 (詳細は [Multi-runtime バックエンド](./multi-runtime.md) を参照):

![Runtime selector](/img/web-ui/11_runtime_selector.png)

### Ask Claude about this finding (CLI spec §3.1.6)

Findings 詳細の **Ask Claude about this finding** ボタンで Chat を開き、finding の context (severity / verdict / file::line / evidence_snippet など) を自動 prefill します。

### Context cap (CLI spec §8.5)

Prefill される context block は **50 KB バイト** で truncate (TextEncoder ベース、multi-byte 安全)。超過時は `…(context truncated to 50 KB budget…)` マーカーを残してモデル側にも明示します。

### Approval gate (3 層)

Chat から起動可能な side-effect tool (`launch_pipeline` / `stop_pipeline`) は 3 層で保護:

1. SDK の `tools=` 引数は read-only allowlist のみ
2. ストリーム上で `tool_use` が来るたびに name を再チェック (allowlist 外なら `tool_not_allowed` を発火して terminate)
3. フロントの `<ToolCard>` で型ベースの再判定

## UX / 設定

### テーマ (CLI spec §10.5)

`light` / `dark` / `system` / **`solarized`** の 4 種。Solarized は Ethan Schoonover の正準パレットを Nyx tokens に重ねたもの。Prism シンタックスハイライトも追従:

| Default | Solarized |
| --- | --- |
| ![dashboard default](/img/web-ui/01_dashboard_default.png) | ![dashboard solarized](/img/web-ui/02_solarized_dashboard.png) |

ヘッダの `L D A S` ボタンで 4-way 切替:

![Theme toggle 4 buttons](/img/web-ui/09_settings_theme_4buttons.png)

### i18n (EN / JA)

i18next で全画面の文言を切替。ヘッダで `EN` / `JA` ボタンから。

### Diagnostics (`/diagnostics`)

`speca doctor` 相当の環境チェックページ。Node / uv / git / claude / gh / VSCode CLI の有無 + バージョン、auth 状況、MCP server 接続状況を一覧。

## エラー処理

### 7 ケース エラーモーダル (CLI spec §10.4)

新規 run 起動時に backend が返す典型エラー (`clone_failed` / `invalid_target_repo` / `ref_not_found` / `worktree_failed` / `anthropic_unreachable` / `run_not_found` / `still_running` / `invalid_phases` / `invalid_workspace_input`) は、`ErrorModal` で title + 説明 + 対処を i18n 経由で表示します。Retry / Close + 「技術的な詳細」disclosure で raw envelope も copy/paste 可能。

## Init config 永続化 (CLI spec §3.1 `speca init`)

新規 run を作成すると、`outputs/<run_id>/TARGET_INFO.json` と `BUG_BOUNTY_SCOPE.json` を Wizard の入力から即座に書き出します。Phase 0a / 0c が後で上書きしますが、最初の stub は `speca init` 同等で、外部ツールから検査可能です。

## キーボードショートカット 全リスト (CLI spec §10.3)

![Keyboard shortcuts help modal](/img/web-ui/08_keyboard_shortcuts_help.png)

| キー | スコープ | 動作 |
| --- | --- | --- |
| `?` | global | ヘルプモーダル |
| `Esc` | global | 開いているモーダル / Chat を閉じる |
| `c` | global | Chat 開閉 |
| `g r` | global | `/runs` へ |
| `g s` | global | `/settings` へ |
| `g d` | global | `/diagnostics` へ |
| `/` | findings | フィルタ入力にフォーカス |
| `j` / `k` | findings | 次 / 前の行へ |
| `Enter` / `Space` | phase 行 | 展開 |
| `l` | phase 行 | 展開 + ログ scroll |
| `f` | phase 行 | force re-run |

すべて IME-safe (composition 中は発火しない)。

## モバイル対応

≤720px でヘッダが折り返し、`runs` テーブルは横スクロール、Findings 一覧は縦に積みます。

## アーキテクチャまとめ

```
ブラウザ
   │  WebSocket + REST
   ▼
FastAPI (web/server/)
   │  subprocess
   ▼
scripts/run_phase.py  ─── ClaudeRunner / APIRunner / CodexAPIRunner ...
                                                │
                                                ▼
                                          各 LLM API
```

詳しいスライス図 / API 一覧は [UI_DESIGN.md](https://github.com/NyxFoundation/speca/blob/dev/docs/UI_DESIGN.md) を参照してください。
