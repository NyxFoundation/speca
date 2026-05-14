---
sidebar_position: 10
---

# Multi-runtime バックエンド

SPECA は claude 以外のエージェント実行系も切替可能です。Chat パネルと audit pipeline 本体それぞれで、複数のバックエンドから選べます。

:::tip 位置づけ
SPECA は **CLI Client** であり、各バックエンドの公式 CLI / API を薄く呼び出します。認証はバックエンドそれぞれの仕組み (claude CLI / codex CLI / API キー / etc.) に委譲し、SPECA 側では Settings の選択と環境変数で切替えます。
:::

## 対応バックエンド一覧

| Runtime | Chat パネル | Audit pipeline | 認証 | デフォルトモデル |
| --- | --- | --- | --- | --- |
| **claude** (既定) | ✅ SDK or CLI subprocess | ✅ ClaudeRunner (stream-json + MCP) | `ANTHROPIC_API_KEY` or `claude auth login` | `claude-sonnet-4-6` |
| **api** (OpenRouter 等) | — | ✅ APIRunner | `API_RUNNER_API_KEY` | `deepseek/deepseek-r1` |
| **codex** | ✅ `codex exec --json` | 🟡 stub (PR #67 で実装予定) | `codex login` or `OPENAI_API_KEY` | `gpt-4o` |
| **gemini** | ✅ `gemini -p --output-format stream-json` | 🟡 stub (PR #67 で実装予定) | `GEMINI_API_KEY` | `gemini-2.0-flash` |
| **ollama** | ✅ HTTP `/api/chat` | 🟡 stub (PR #67 で実装予定) | `OLLAMA_API_KEY` (cloud) / 不要 (self-hosted) | `llama3.2` |
| **copilot** | ✅ `gh copilot suggest` (単発) | ❌ 非対応 (tool-calling API なし) | `gh auth login` + Copilot 契約 | — |

:::note PR #67 マージ後の状態
PR #67 がマージされると codex / gemini / ollama も audit pipeline 側で完全対応します。Copilot は引き続き Chat パネル専用です (`gh copilot suggest` が tool-calling API を持たないため、audit phase の Read/Grep/Glob/Write 駆動ができません)。
:::

## CLI で runtime を選ぶ

### 一覧と availability の確認

```bash
uv run python scripts/run_phase.py --list-runtimes
```

CLI / 環境変数 / 認証状況を見て、各バックエンドが今すぐ使えるかをまとめて表示します。

```text
Active runtime: claude  (ORCHESTRATOR_RUNNER env / --runtime flag)

[OK] claude
     Anthropic claude CLI (stream-json). Production audit path.
     - claude CLI ready.

[..] api
     OpenRouter-style HTTP (OPENAI_API_KEY-compatible). Non-Claude models.
     - Set API_RUNNER_API_KEY to authenticate.

[..] codex (stub)
     OpenAI codex CLI (`codex exec --json`). Registered but stubbed.
     - codex CLI present; run `codex login`.
     - Note: orchestrator runner not yet implemented (Web chat works today).

...
```

JSON で吐かせたい場合 (`speca-cli` や CI から消費する用):

```bash
uv run python scripts/run_phase.py --list-runtimes --json | python -m json.tool
```

### 実行時に runtime を指定する

```bash
uv run python scripts/run_phase.py --target 04 --runtime api --workers 4
```

`--runtime` は `ORCHESTRATOR_RUNNER` 環境変数を上書きするので、1 つのコマンドで再現可能です。Stub の runtime を指定すると exit 2 で停止し、silent fallback で誤った PARTIAL を吐くことがありません:

```bash
uv run python scripts/run_phase.py --target 04 --runtime codex
# →
# ERROR: runtime 'codex' cannot drive the orchestrator.
# OpenAI codex CLI (`codex exec --json`). Registered but stubbed.
# Notes:
#   - codex CLI present; run `codex login`.
#   - Note: orchestrator runner not yet implemented (Web chat works today).
# exit code: 2
```

## Web UI で runtime を選ぶ

`/settings` ページに **Chat runtime** セクションがあります。5 つのボタンから選び、`(✓)` / `(!)` バッジで可用性 (CLI が PATH 上にあるか、API キーが設定されているか) が一目で分かります。

選択は `~/.speca/runtime.json` に永続化されるので、サーバ再起動でも保持されます。秘密情報 (API キー) はこの設定ファイルには入りません — `OLLAMA_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` などはサーバプロセスの環境変数から読みます。

### Advanced — model / host 上書き

`Chat runtime` セクションの `Advanced — per-runtime model / host` を展開すると、各 runtime のデフォルトモデルや Ollama host を変更できます:

- `Claude model override` (例: `claude-opus-4-7`)
- `Codex model override`
- `Gemini model override` (例: `gemini-2.5-pro`)
- `Ollama host` (`https://ollama.com` または `http://localhost:11434`)
- `Ollama model` (例: `llama3.2:70b`)

## バックエンド別セットアップ

### Claude (既定)

```bash
npm install -g @anthropic-ai/claude-code
claude auth login        # claude.ai OAuth or API key
```

Pro / Max サブスクリプションを使う場合は OAuth、それ以外は `ANTHROPIC_API_KEY` を export。

### Codex (OpenAI)

```bash
npm install -g @openai/codex
codex login              # ChatGPT plan
# あるいは
printenv OPENAI_API_KEY | codex login --with-api-key
```

PR #67 マージ後は audit pipeline 側で `OPENAI_API_KEY` 環境変数を直接使うので、codex CLI のインストール自体は orchestrator では不要 (Chat 側では引き続き使用)。

### Gemini

```bash
npm install -g @google/gemini-cli
export GEMINI_API_KEY=...   # Google AI Studio で発行
```

### Ollama

**Cloud:**

```bash
export OLLAMA_HOST=https://ollama.com
export OLLAMA_API_KEY=...
```

**Self-hosted:**

```bash
ollama serve              # localhost:11434 で起動
export OLLAMA_HOST=http://localhost:11434
# OLLAMA_API_KEY は不要
ollama pull llama3.2
```

### GitHub Copilot (Chat のみ)

```bash
# GitHub CLI を導入し、Copilot を有効化
gh auth login
gh extension install github/gh-copilot
```

Chat パネルでのみ動作します。audit pipeline は非対応。

## 既知の制限

- **Phase 02c (MCP tree-sitter)** — 現状 `claude` runtime だけが MCP server (`mcp__tree_sitter__*`) を起動できます。`codex` / `gemini` / `ollama` で Phase 02c を回すと code pre-resolution の精度が落ちます。回避策:
  - `--phase 01a 01b 01e 03 04` のように 02c をスキップ
  - 02c だけ `--runtime claude`、残りを別 runtime で split run
- **Audit 結果の再現性** — runtime ごとにモデルが違うので、同一 commit でも findings の量・質は変動します。比較ベンチは benchmark スイート (`benchmarks/`) で別途取得してください。
- **Cost tracker** — APIRunner 系は OpenAI 互換 response の `usage` から計算しますが、self-hosted Ollama は `total_cost_usd = 0` になります (ローカル推論なので)。
