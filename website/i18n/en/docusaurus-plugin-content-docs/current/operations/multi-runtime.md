---
sidebar_position: 10
---

# Multi-runtime backends

SPECA can drive more than one agentic backend. Both the chat panel and
the audit pipeline accept a runtime selector.

:::tip Positioning
SPECA is a **CLI Client** — it shells out to each backend's official CLI
/ API. Authentication stays with the backend (`claude auth login`,
`codex login`, an API key, …); SPECA only owns the *selection* via
Settings or an env var.
:::

## Supported runtimes

| Runtime | Chat panel | Audit pipeline | Auth | Default model |
| --- | --- | --- | --- | --- |
| **claude** (default) | ✅ SDK or CLI subprocess | ✅ ClaudeRunner (stream-json + MCP) | `ANTHROPIC_API_KEY` or `claude auth login` | `claude-sonnet-4-6` |
| **api** (OpenRouter / etc.) | — | ✅ APIRunner | `API_RUNNER_API_KEY` | `deepseek/deepseek-r1` |
| **codex** | ✅ `codex exec --json` | 🟡 stub (PR #67) | `codex login` or `OPENAI_API_KEY` | `gpt-4o` |
| **gemini** | ✅ `gemini -p --output-format stream-json` | 🟡 stub (PR #67) | `GEMINI_API_KEY` | `gemini-2.0-flash` |
| **ollama** | ✅ HTTP `/api/chat` | 🟡 stub (PR #67) | `OLLAMA_API_KEY` (cloud) / none (self-hosted) | `llama3.2` |
| **copilot** | ✅ `gh copilot suggest` (single-shot) | ❌ unsupported (no tool-calling API) | `gh auth login` + Copilot subscription | — |

:::note After PR #67 lands
codex / gemini / ollama become fully usable on the audit pipeline side
too. Copilot stays chat-only because `gh copilot suggest` has no
tool-calling API and cannot drive Read/Grep/Glob/Write phases.
:::

## Pick a runtime from the CLI

### List availability

```bash
uv run python scripts/run_phase.py --list-runtimes
```

The output shows each backend with its install / auth status:

```text
Active runtime: claude  (ORCHESTRATOR_RUNNER env / --runtime flag)

[OK] claude
     Anthropic claude CLI (stream-json). Production audit path.
     - claude CLI ready.

[..] codex (stub)
     OpenAI codex CLI (`codex exec --json`). Registered but stubbed.
     - codex CLI present; run `codex login`.
     - Note: orchestrator runner not yet implemented (Web chat works today).

...
```

JSON mode (for CI / speca-cli consumers):

```bash
uv run python scripts/run_phase.py --list-runtimes --json | python -m json.tool
```

### Choose at run time

```bash
uv run python scripts/run_phase.py --target 04 --runtime api --workers 4
```

`--runtime` overrides `ORCHESTRATOR_RUNNER`. Selecting a stub aborts
with exit 2 instead of silently falling back to claude — so you never
generate misleading PARTIALs:

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

## Pick a runtime from the Web UI

`/settings` has a **Chat runtime** section with five buttons. Each
shows a `(✓)` / `(!)` badge for availability (CLI on PATH, API key in
env). The choice persists to `~/.speca/runtime.json` across server
restarts. Secrets never go through the API — `OLLAMA_API_KEY` /
`OPENAI_API_KEY` / `GEMINI_API_KEY` are read from the server process
env at request time.

### Advanced — model / host overrides

Expand **Advanced — per-runtime model / host** to set:

- `Claude model override` (e.g. `claude-opus-4-7`)
- `Codex model override`
- `Gemini model override` (e.g. `gemini-2.5-pro`)
- `Ollama host` (`https://ollama.com` or `http://localhost:11434`)
- `Ollama model` (e.g. `llama3.2:70b`)

## Per-backend setup

### Claude (default)

```bash
npm install -g @anthropic-ai/claude-code
claude auth login        # claude.ai OAuth or API key
```

Pro/Max subscribers use OAuth; otherwise export `ANTHROPIC_API_KEY`.

### Codex (OpenAI)

```bash
npm install -g @openai/codex
codex login              # ChatGPT plan
# or
printenv OPENAI_API_KEY | codex login --with-api-key
```

After PR #67 the orchestrator reads `OPENAI_API_KEY` directly, so the
codex CLI itself is only needed for the chat side.

### Gemini

```bash
npm install -g @google/gemini-cli
export GEMINI_API_KEY=...   # from Google AI Studio
```

### Ollama

**Cloud:**

```bash
export OLLAMA_HOST=https://ollama.com
export OLLAMA_API_KEY=...
```

**Self-hosted:**

```bash
ollama serve              # localhost:11434
export OLLAMA_HOST=http://localhost:11434
ollama pull llama3.2
```

### GitHub Copilot (chat only)

```bash
gh auth login
gh extension install github/gh-copilot
```

Chat panel only — audit pipeline is unsupported.

## Known limits

- **Phase 02c (MCP tree-sitter)** — only `claude` runs the MCP
  `mcp__tree_sitter__*` servers. Other runtimes reduce code
  pre-resolution accuracy. Workarounds: skip 02c
  (`--phase 01a 01b 01e 03 04`), or run 02c under `--runtime claude`
  and the rest under another runtime.
- **Reproducibility** — different models give different findings;
  benchmark via `benchmarks/`.
- **Cost tracker** — APIRunner reads `usage` off the OpenAI-compatible
  response, so self-hosted Ollama reports `total_cost_usd = 0` (local
  inference, no per-token charge).
