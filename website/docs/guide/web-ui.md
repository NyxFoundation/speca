---
sidebar_position: 5
---

# Web UI

SPECA は CLI 中心の道具ですが、`speca-web` でブラウザから操作できる Web UI も同梱しています。位置づけはあくまで **CLI Client** — `scripts/run_phase.py` や `speca-cli` (issue #3) と同じ操作をブラウザで行うためのフロントエンドです。

## できること

- 過去の audit run の一覧と詳細を眺める
- Phase の進捗を WebSocket でリアルタイム表示
- Findings をフィルタ / ソート / Markdown でエクスポート
- 新規 audit を Picker / Wizard から起動
- Chat パネルから Claude / Codex / Gemini / Ollama / Copilot と対話
- Settings から実行 runtime / テーマ / 言語を切替

詳細な機能一覧は [Web UI の機能](../operations/web-ui-features.md) を、runtime 切替の詳細は [Multi-runtime バックエンド](../operations/multi-runtime.md) を参照してください。

## 起動

```bash
uv run speca-web --port 7411 --host 127.0.0.1 --serve-frontend
```

`http://127.0.0.1:7411/` を開けばダッシュボードが表示されます。claude.ai OAuth でログイン済 (`claude auth status` が `logged_in=true` を返す状態) であれば、自動的にダッシュボードへ。未ログインなら login 画面が表示され、ブラウザから paste-code OAuth or API キー入力で認証できます。

## ローカル限定で動かす

既定では `127.0.0.1` のみで bind し、LAN 経由のアクセスは受け付けません。同一マシン上のローカル使用前提です。

LAN 経由で使いたい場合は `--host 0.0.0.0` を明示してください (環境次第ですが、Firewall / NAT で守られていない環境では非推奨)。

## ショートカット

| キー | 動作 |
| --- | --- |
| `?` | キーボードショートカット一覧モーダル |
| `Esc` | 開いているモーダル / Chat パネルを閉じる |
| `c` | Chat パネルの開閉 |
| `g r` / `g s` / `g d` | Runs / Settings / Diagnostics へ |
| `/` | Findings filter にフォーカス |
| `j` / `k` | Findings 行を次 / 前へ |
| Phase 行 focus 中: `l` / `f` | ログ展開 / その phase だけ force re-run |

## アーキテクチャ

- **バックエンド** — FastAPI + uvicorn (`web/server/`)。`scripts/run_phase.py` をサブプロセスで呼んで pipeline を駆動。orchestrator の Python コードを直接 import はしません (decoupling)。
- **フロントエンド** — React 19 + TypeScript + Vite (`web/frontend/`)。TanStack Query で REST + WebSocket、Zustand で UI state、i18next で EN/JA。
- **状態保持** — Run state は `.speca/runs/<run_id>/state.json`、Chat 履歴は `~/.speca/chat/<conversation_id>.json`、Runtime 設定は `~/.speca/runtime.json`。秘密情報はどれにも入りません。

## 関連ドキュメント

- [はじめに / インストール](../getting-started/installation.md)
- [Web UI の機能](../operations/web-ui-features.md)
- [Multi-runtime バックエンド](../operations/multi-runtime.md)
