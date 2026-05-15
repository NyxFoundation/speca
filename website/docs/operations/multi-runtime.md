---
sidebar_position: 10
---

# Multi-runtime バックエンド

SPECA は **claude / codex / gemini / ollama / copilot** + 汎用 `api` (OpenRouter-style) の **6 backend** に対応しています。Chat パネルと audit pipeline それぞれで、どの backend を使うかを Settings or 環境変数で選べます。

![Runtime selector in Settings](/img/web-ui/11_runtime_selector.png)

:::tip 位置づけ
SPECA は **CLI Client** であり、各バックエンドの公式 CLI / API を薄く呼び出します。認証はバックエンドそれぞれの仕組み (claude CLI / codex CLI / API キー / etc.) に委譲し、SPECA 側では Settings の選択と環境変数で切替えます。
:::

## 対応一覧

| Runtime | Chat パネル | Audit pipeline | 認証 | デフォルトモデル |
| --- | --- | --- | --- | --- |
| **claude** (既定) | ✅ SDK or CLI subprocess | ✅ ClaudeRunner (stream-json + MCP) | `ANTHROPIC_API_KEY` or `claude auth login` | `claude-sonnet-4-6` |
| **api** (OpenRouter 等) | — | ✅ APIRunner | `API_RUNNER_API_KEY` | `deepseek/deepseek-r1` |
| **codex** | ✅ `codex exec --json` | ✅ CodexAPIRunner (APIRunner サブクラス) | `codex login` or `OPENAI_API_KEY` | `gpt-4o` |
| **gemini** | ✅ `gemini -p --output-format stream-json` | ✅ GeminiAPIRunner (OpenAI 互換 endpoint) | `GEMINI_API_KEY` | `gemini-2.0-flash` |
| **ollama** | ✅ HTTP `/api/chat` | ✅ OllamaAPIRunner (`<host>/v1/chat/completions`) | `OLLAMA_API_KEY` (cloud) / 不要 (self-hosted) | `llama3.2` |
| **copilot** | ✅ `@github/copilot` agentic CLI | 🟡 stub (CopilotRunner サブクラスは follow-up) | `copilot` CLI 初回起動時に GitHub OAuth | — |

:::note Copilot の位置づけ
`@github/copilot` agentic CLI (`copilot -p --output-format json`) は tool-calling 対応のため、orchestrator 側でも技術的には駆動可能です。現状 `implemented=False` のままなのは **scope choice (follow-up PR で CopilotRunner を実装予定)** であり、`gh copilot suggest` 時代の「fundamental に不可能」という制約ではありません。
:::

---

## バックエンド別 深掘り

### Claude (既定)

Anthropic Claude。チャットでは API key ユーザは SDK、claude.ai OAuth (Pro/Max サブスクライバー) は CLI subprocess 経由になります。Audit pipeline は ClaudeRunner で stream-json + MCP tree-sitter を含むフル機能。

```bash
npm install -g @anthropic-ai/claude-code
claude auth login        # claude.ai OAuth (Pro/Max) or API key
```

OAuth 用トークンは `~/.claude/.credentials.json` に保存。API key を使う場合は `ANTHROPIC_API_KEY` を export するか Web UI の login 画面から入力できます。

**Pro / Max + Web UI 統合:**
ログイン状態は paste-code OAuth flow でブラウザから完結:

![Login paste-code OAuth](/img/web-ui/10_login_paste_code.png)

詳細は CLI spec §4.5.1 + [Web UI 機能ページ](./web-ui-features.md#paste-code-oauth-cli-spec-451) を参照。

### Codex (OpenAI)

OpenAI 公式の `codex` CLI 経由 (Chat) または `OPENAI_API_KEY` 経由 (Audit)。Codex CLI は ChatGPT plan のサブスクリプションでも API key でも認証できます:

```bash
npm install -g @openai/codex

# ChatGPT plan を使う
codex login

# あるいは API key を使う
printenv OPENAI_API_KEY | codex login --with-api-key
```

**Chat 側 (現状で動作):**
`codex exec --json` をサブプロセスで起動。`--resume <session_id>` でマルチターンの context を継続。tool は `--sandbox read-only` で限定。

**Audit pipeline 側:**
codex CLI のインストールは **不要**。`OPENAI_API_KEY` だけで `https://api.openai.com/v1` を直接叩く CodexAPIRunner (APIRunner のサブクラス) が、既存の Read / Grep / Glob / Write tool 関数呼び出しループをそのまま使い回します。

| 環境変数 | 既定値 | 用途 |
|---|---|---|
| `OPENAI_API_KEY` | (必須) | API 認証 |
| `OPENAI_MODEL` | `gpt-4o` | モデル指定 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | エンドポイント上書き (Azure OpenAI 等) |

### Gemini (Google)

Google AI Studio の `gemini` CLI 経由 (Chat) または **OpenAI 互換エンドポイント** 経由 (Audit):

```bash
npm install -g @google/gemini-cli
export GEMINI_API_KEY=...   # https://aistudio.google.com/apikey で発行
```

**Chat 側:**
`gemini -p <prompt> --output-format stream-json --approval-mode plan` をサブプロセス起動。`--approval-mode plan` で read-only モードに固定 (chat パネルは安全)。tolerant parser が stream-json の複数 event shape (text / delta / content / candidates.content.parts[].text) をすべて受け付けます。

**Audit pipeline 側:**
GeminiAPIRunner が `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions` を叩きます。OpenAI 関数呼び出し形と完全互換なので、APIRunner のループがそのまま動作。

| 環境変数 | 既定値 | 用途 |
|---|---|---|
| `GEMINI_API_KEY` | (必須) | API 認証 |
| `GEMINI_MODEL` | `gemini-2.0-flash` | モデル指定 (`gemini-2.5-pro` 等) |
| `GEMINI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai` | endpoint 上書き |

### Ollama (cloud + self-hosted)

**Self-hosted:**

```bash
ollama serve              # localhost:11434 で起動
ollama pull llama3.2
export OLLAMA_HOST=http://localhost:11434
# OLLAMA_API_KEY は不要 (ローカル)
```

**Cloud:**

```bash
export OLLAMA_HOST=https://ollama.com
export OLLAMA_API_KEY=...   # https://ollama.com で発行
```

**Chat 側:**
HTTP `/api/chat` (NDJSON streaming) を `httpx.AsyncClient` で叩きます。会話履歴は最新 20 turns を再送 (Ollama はステートレス)。

**Audit pipeline 側:**
Ollama 公式の OpenAI 互換エンドポイント `<host>/v1/chat/completions` 経由。OllamaAPIRunner が `OLLAMA_HOST` から base_url を派生し、self-hosted (`http://localhost:11434/v1`) / cloud (`https://ollama.com/v1`) どちらでも統一的に動きます。

| 環境変数 | 既定値 | 用途 |
|---|---|---|
| `OLLAMA_HOST` | `https://ollama.com` | host (cloud or self-hosted) |
| `OLLAMA_API_KEY` | (cloud 時必須) | Bearer トークン (cloud のみ) |
| `OLLAMA_MODEL` | `llama3.2` | モデル指定 (`llama3.2:70b` 等) |
| `OLLAMA_BASE_URL` | `<OLLAMA_HOST>/v1` 自動派生 | endpoint 上書き |

:::info self-hosted Ollama の cost
APIRunner の cost_tracker は OpenAI 互換 response の `usage` から計算します。self-hosted Ollama では `total_cost_usd = 0` になります (ローカル推論なので) — 仕様通りです。
:::

### GitHub Copilot

`@github/copilot` agentic CLI 経由。Chat 側は本実装、Audit pipeline 側は **scope choice の follow-up** で現状 stub。

```bash
npm install -g @github/copilot
copilot                       # 初回起動時に GitHub OAuth (~/.copilot に creds 永続)
```

**Chat 側 (現状で動作):**
`copilot -p <prompt> --output-format json --allow-all-tools --no-banner` をサブプロセス起動し、JSONL イベントを SSE に変換してクライアントへ流します。tool_use イベントは circuit breaker / approval gate を通ります。旧 `gh copilot suggest` shim は廃止済み (PR #73)。

**Audit pipeline 側 (follow-up):**
agentic CLI 自体は tool-calling 対応なので技術的には orchestrator から駆動可能ですが、CopilotRunner サブクラス (JSONL イベントを既存 CircuitBreaker / CostTracker に流し込む) はまだ書かれていません。現状 `--runtime copilot` は CLI レベルで exit 2 を返します。

### api (OpenRouter / DeepSeek / 任意 OpenAI 互換)

汎用 OpenAI 互換 HTTP runner。OpenRouter / DeepSeek 等、任意のエンドポイントを `API_RUNNER_BASE_URL` で指定:

```bash
export API_RUNNER_API_KEY=sk-or-v1-...
export API_RUNNER_BASE_URL=https://openrouter.ai/api/v1
export API_RUNNER_MODEL=deepseek/deepseek-r1
```

audit pipeline 専用 (Chat 側では使わない)。

---

## CLI で runtime を選ぶ

### 一覧と availability の確認

```bash
uv run python scripts/run_phase.py --list-runtimes
```

CLI / 環境変数 / 認証状況を見て、各バックエンドが今すぐ使えるかをまとめて表示します:

```text
Active runtime: claude  (ORCHESTRATOR_RUNNER env / --runtime flag)

[OK] claude
     Anthropic claude CLI (stream-json). Production audit path.
     - claude CLI ready.

[..] api
     OpenRouter-style HTTP (OPENAI_API_KEY-compatible). Non-Claude models.
     - Set API_RUNNER_API_KEY to authenticate.

[..] codex
     OpenAI Chat API (codex CLI authenticates against this). Tool-calling enabled.
     - Routes through CodexAPIRunner -> https://api.openai.com/v1
     - OPENAI_MODEL: gpt-4o
     - Set OPENAI_API_KEY to authenticate.

[OK] copilot (stub)
     GitHub Copilot agentic CLI (`copilot -p --output-format json`). Web chat works today; orchestrator runner is a follow-up.
     - copilot CLI on PATH.
     - Note: orchestrator runner not yet implemented (Web chat works today).
```

JSON で吐かせたい場合 (`speca-cli` や CI から消費する用):

```bash
uv run python scripts/run_phase.py --list-runtimes --json | python -m json.tool
```

### 実行時に runtime を指定する

```bash
# OpenRouter 経由
uv run python scripts/run_phase.py --target 04 --runtime api --workers 4

# codex / gemini / ollama 経由
uv run python scripts/run_phase.py --target 04 --runtime codex
uv run python scripts/run_phase.py --target 04 --runtime gemini -c model=gemini-2.5-pro
uv run python scripts/run_phase.py --target 04 --runtime ollama
```

`--runtime` は `ORCHESTRATOR_RUNNER` 環境変数を上書きするので、1 つのコマンドで再現可能です。Stub の runtime (現状 copilot のみ) を指定すると exit 2 で停止し、silent fallback で誤った PARTIAL を吐くことがありません:

```bash
uv run python scripts/run_phase.py --target 04 --runtime copilot
# →
# ERROR: runtime 'copilot' cannot drive the orchestrator.
# GitHub Copilot agentic CLI (`copilot -p --output-format json`). Web chat works today; orchestrator runner is a follow-up.
# Notes:
#   - copilot CLI on PATH.
#   - Copilot subscription required.
#   - Note: orchestrator runner not yet implemented (Web chat works today).
# exit code: 2
```

---

## Web UI で runtime を選ぶ

`/settings` ページの **Chat runtime** セクションで切替えます:

![Runtime selector in Settings](/img/web-ui/11_runtime_selector.png)

- 5 つのボタン (Claude / Codex / Gemini / Ollama / Copilot) と availability badge (`✓` / `!`)
- 選択中 runtime の状態 hint (CLI 未導入 / login 必要 / 鍵未設定 / 利用可能 等を一言で)
- **Advanced — per-runtime model / host** 折り畳みで model 上書き + Ollama host を編集
- 設定は `~/.speca/runtime.json` に永続化 (秘密情報は入りません)

API キー (`OLLAMA_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY`) はサーバプロセスの環境変数から読みます — Settings ファイルには保存しないので、共有マシンでも安全です。

---

## 既知の制限

- **Phase 02c (MCP tree-sitter)** — 現状 `claude` runtime だけが MCP server (`mcp__tree_sitter__*`) を起動できます。`codex` / `gemini` / `ollama` で Phase 02c を回すと code pre-resolution の精度が落ちます。回避策:
  - `--phase 01a 01b 01e 03 04` のように 02c をスキップ
  - 02c だけ `--runtime claude`、残りを別 runtime で split run
- **Audit 結果の再現性** — runtime ごとにモデルが違うので、同一 commit でも findings の量・質は変動します。比較ベンチは benchmark スイート (`benchmarks/`) で別途取得してください。
- **Cost tracker** — APIRunner 系は OpenAI 互換 response の `usage` から計算しますが、self-hosted Ollama は `total_cost_usd = 0` になります (ローカル推論なので)。
- **Copilot は audit pipeline 側 stub** — `@github/copilot` agentic CLI 自体は tool-calling 対応なので技術的に駆動可能ですが、CopilotRunner サブクラスは未実装。`--runtime copilot` は exit 2 で reject されます。Chat パネル側は本実装で利用可能。
