---
sidebar_position: 5
---

# Web UI

SPECA は CLI 中心の道具ですが、`speca-web` でブラウザから操作できる Web UI も同梱しています。位置づけはあくまで **CLI Client** — `scripts/run_phase.py` や `speca-cli` ([issue #3](https://github.com/NyxFoundation/speca/issues/3)) と同じ操作をブラウザで行うためのフロントエンドです。

![SPECA dashboard](/img/web-ui/01_dashboard_default.png)

## できること

- 過去の audit run の一覧と詳細を眺める
- Phase の進捗を WebSocket でリアルタイム表示
- Findings をフィルタ / ソート / Markdown でエクスポート
- 新規 audit を Picker / Wizard から起動
- Chat パネルから **Claude / Codex / Gemini / Ollama / Copilot** と対話 (Settings で切替)
- Settings から実行 runtime / テーマ (light/dark/system/**solarized**) / 言語 (EN/JA) を切替

詳細な機能一覧は [Web UI の機能](../operations/web-ui-features.md) を、runtime 切替の詳細は [Multi-runtime バックエンド](../operations/multi-runtime.md) を参照してください。

## 起動

```bash
uv run speca-web --port 7411 --host 127.0.0.1 --serve-frontend
```

`http://127.0.0.1:7411/` を開けばダッシュボードが表示されます。claude.ai OAuth でログイン済 (`claude auth status` が `logged_in=true` を返す状態) であれば、自動的にダッシュボードへ。未ログインなら paste-code OAuth or API キー入力で認証できます:

![Login screen with paste-code OAuth](/img/web-ui/10_login_paste_code.png)

## ローカル限定で動かす

既定では `127.0.0.1` のみで bind し、LAN 経由のアクセスは受け付けません。同一マシン上のローカル使用前提です。LAN 経由で使いたい場合は `--host 0.0.0.0` を明示してください (環境次第ですが、Firewall / NAT で守られていない環境では非推奨)。

## Run 詳細 — phase 進捗 + 予算ゲージ

![Run detail with phase rows and budget gauge](/img/web-ui/05_run_detail_budget_phases.png)

各 phase 行は折り畳み可能。focus 中に `l` を押せばログペインへ scroll、`f` で当該 phase だけ force re-run できます。予算ゲージをクリックすると **cap-bump モーダル** が開いて `max_budget_usd` を引き上げ / クリアできます:

![Budget cap-bump modal](/img/web-ui/06_budget_cap_bump_modal.png)

## Findings — DSL filter + コードハイライト

Findings 一覧は severity / verdict / phase chip でサーバ側フィルタ、追加の DSL 入力でクライアント側のさらに細かい filter (path glob 等) ができます。Markdown export も。

![Findings list](/img/web-ui/03_findings_list.png)

行をクリックすると詳細ページで evidence_snippet が Prism でシンタックスハイライトされます (Solidity / TS / JS / Python / Rust / Go / Java / C / C++):

![Finding detail with code highlight](/img/web-ui/04_finding_detail_code_highlight.png)

## Chat パネル — multi-runtime 対応

右側の **Chat** ボタン (またはキーボードショートカット `c`) でチャットパネルが開きます:

![Chat panel](/img/web-ui/07_chat_panel_empty.png)

会話の駆動先は Settings ページから 5 backend (**Claude / Codex / Gemini / Ollama / Copilot**) のいずれかを選べます。詳しくは [Multi-runtime バックエンド](../operations/multi-runtime.md) を参照。

## Settings — runtime / テーマ / 言語

![Runtime selector in Settings](/img/web-ui/11_runtime_selector.png)

**Chat runtime** セクションで 5 backend を切替、availability badge (`✓` / `!`) で各 backend がすぐ使えるかが一目で分かります。Advanced を展開すれば runtime ごとの model / Ollama host を上書き可能。

テーマは light / dark / system に加えて **Solarized** に対応:

| Default | Solarized |
| --- | --- |
| ![dashboard default](/img/web-ui/01_dashboard_default.png) | ![dashboard solarized](/img/web-ui/02_solarized_dashboard.png) |

ヘッダの `L D A S` ボタンで 4-way 切替:

![Theme toggle 4 buttons](/img/web-ui/09_settings_theme_4buttons.png)

## ショートカット

`?` を押すといつでも一覧モーダルが出ます:

![Keyboard shortcuts help](/img/web-ui/08_keyboard_shortcuts_help.png)

| キー | 動作 |
| --- | --- |
| `?` | キーボードショートカット一覧モーダル |
| `Esc` | 開いているモーダル / Chat パネルを閉じる |
| `c` | Chat パネルの開閉 |
| `g r` / `g s` / `g d` | Runs / Settings / Diagnostics へ |
| `/` | Findings filter にフォーカス |
| `j` / `k` | Findings 行を次 / 前へ |
| Phase 行 focus 中: `l` / `f` | ログ展開 / その phase だけ force re-run |

すべて IME-safe (composition 中は発火しない)。

## アーキテクチャ

- **バックエンド** — FastAPI + uvicorn (`web/server/`)。`scripts/run_phase.py` をサブプロセスで呼んで pipeline を駆動。orchestrator の Python コードを直接 import はしません (decoupling)。
- **フロントエンド** — React 19 + TypeScript + Vite (`web/frontend/`)。TanStack Query で REST + WebSocket、Zustand で UI state、i18next で EN/JA。
- **状態保持** — Run state は `.speca/runs/<run_id>/state.json`、Chat 履歴は `~/.speca/chat/<conversation_id>.json`、Runtime 設定は `~/.speca/runtime.json`。秘密情報はどれにも入りません。

## 関連ドキュメント

- [はじめに / インストール](../getting-started/installation.md)
- [Web UI の機能 (全網羅)](../operations/web-ui-features.md)
- [Multi-runtime バックエンド](../operations/multi-runtime.md)
