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
[Browser SPA (React + Vite)]
   │  HTTP / WebSocket (127.0.0.1 のみ listen)
   ▼
[Backend (FastAPI, Python)]
   ├─ subprocess ──► scripts/run_phase.py
   ├─ git plumbing ► audit/<target>/<run-id> branch
   └─ filesystem ──► outputs/ , .speca/runs/<run-id>/
```

- backend は SPECA 同梱 (`web/server/` 等)、起動コマンド `uv run speca-web` 想定
- frontend は同 backend が静的配信 (build 成果物を FastAPI が serve)
- バイト送り合うのは JSON のみ、orchestrator 型は import しない

## 3. 技術選定

| レイヤ | 選定 | 理由 |
|---|---|---|
| Backend 言語 | Python (FastAPI) | uv 環境既存、subprocess + ファイル監視で完結する |
| Frontend 言語 | TypeScript | 既存 cli/ (TypeScript) と揃う。schema 型を共有しやすい |
| Frontend フレームワーク | React 19 + Vite | Docusaurus 既存 (React 19) と揃う。Docusaurus 拡張ではなく独立 SPA とする (ローカル限定なので overkill) |
| ルーティング | React Router v6 | ファイルベースでなく宣言的にする (Next.js は overkill) |
| 状態管理 | TanStack Query + Zustand | サーバ状態は Query、UI 状態は Zustand |
| UI コンポーネント | Tailwind CSS + shadcn/ui (radix base) | 軽量、a11y 確保、ダーク対応 |
| リアルタイム | WebSocket | stream-json の行単位 tail に向く |
| 検索 | Fuse.js (client-side fuzzy) | 静的 JSON を読むだけで動く |
| run index | `.speca/runs/<run-id>/manifest.json` (PR #55) | append-only 設計が web UI からの「読むだけ」と相性良い |
| 永続化 (将来) | SQLite (sqlite-utils or sqlmodel) | コメント・編集ログを v5 以降で持つ。orchestrator の outputs/ には触らず web UI 由来の状態のみ |
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
| `/auth/login` | POST | - | OAuth 開始、`claude login` を spawn |
| `/auth/api-key` | POST | `{ key }` | API key を `~/.claude/credentials.json` に書く |
| `/auth/status` | GET | - | `{ logged_in: bool, method: "oauth"\|"api_key" }` |

### 7.2 Backend ↔ Frontend (WebSocket)

- `/ws/runs/<id>/stream` — phase 進捗 / log line / cost 更新を push
- メッセージ schema:
  ```jsonc
  { "type": "phase_progress", "phase": "03", "completed": 24, "total": 50 }
  { "type": "log_line", "phase": "03", "line": "<stream-json line>" }
  { "type": "cost_update", "phase": "03", "snapshot": { ... } }
  { "type": "phase_complete", "phase": "03", "status": "ok" }
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

### 8.1 v0 — Findings 表示のみ

- ログイン (OAuth + API key 両方)
- `.speca/runs/` 一覧 / 切替
- 単一 run の Phase 03 / 04 finding 一覧
- 詳細画面 (基本)
- run 起動・監視は **未対応**

これだけで issue #54 の最小要件は満たせる。

### 8.2 v1 — Run 起動・監視

- 新規 run フォーム
- subprocess spawn + git branch 切る
- WebSocket で進捗 / コスト / ログ tail
- 中断 / 強制再実行

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

## 10. 関連 issue / PR

- issue #54 (本設計の出発点) — Web GUI for browsing SPECA findings + Phase 05 critique traces
- issue #53 — Phase 05 critique 実装 (v3 で対応するデータソース)
- PR #55 — Archive substrate (`.speca/runs/<run-id>/`)、本設計の run index として活用
- PR #52 — Phase B 設計、eval harness の集計を将来 UI に出す余地
- Action `full-audit.yml` — 本 UI の挙動の reference / 仕様契約
