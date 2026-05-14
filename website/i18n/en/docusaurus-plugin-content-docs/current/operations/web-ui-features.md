---
sidebar_position: 11
---

# Web UI features

The `speca-web` frontend mirrors the `speca-cli` TUI from
[issue #3](https://github.com/NyxFoundation/speca/issues/3) in the
browser. This page collects every shipped feature in one place, with
CLI-spec section references so you can map web ↔ TUI.

## Authentication

### Paste-code OAuth (CLI spec §4.5.1)

The login screen's **Continue with claude.ai (paste-code)** button
spawns `claude auth login` server-side, extracts the auth URL from its
stdout, and opens it in a new browser tab. Paste the verification code
back into the SPA form; the server feeds it to the subprocess's stdin
and updates `~/.claude/.credentials.json`.

The legacy "open a separate console" path is kept as a fallback inside
a `<details>` disclosure.

### API key

Users without a subscription can paste an `ANTHROPIC_API_KEY` directly.
It lands in `~/.claude/credentials.json` (note: separate from the CLI's
`.credentials.json`).

## Dashboard / Run detail

### Phase-row keybindings (CLI spec §10.3)

With a phase row focused:

| Key | Action |
| --- | --- |
| `Enter` / `Space` | Expand |
| `l` | Expand + scroll the log pane into view |
| `f` | Force re-run that phase only |
| `s` | Skip (supervisor side not yet wired; handler is in place) |

### Budget gauge + cap-bump modal (CLI spec §5.3.3)

The budget gauge colours by `spent / cap` (yellow at 80%, red at 100%).
Click it to open the **cap-bump modal** and raise / clear
`max_budget_usd`. Persisted via `POST /api/runs/<id>/budget_cap`.

## Findings

### Code highlighting (CLI spec §5.4.4 `[c]`)

Prism highlights `evidence_snippet`. Solidity / TS / JS / Python / Rust
/ Go / Java / C / C++ grammars ship; unknown languages fall through to
plain text. Solarized theme has its own Prism palette.

### Filter DSL (CLI spec §5.4.1)

```
severity:HIGH|CRITICAL verdict:CONFIRMED_VULNERABILITY prop:PROP-6a4* path:src/**/*.sol token1 token2
```

- `severity:` / `verdict:` — OR-list
- `prop:` / `repo:` — glob (`*` / `?`)
- `path:` — `**`-aware path glob
- Free tokens — AND-substring across `property_id` / `file` /
  `proof_trace` / `evidence_snippet` / `reviewer_notes`

### `?glob=` URL parameter (CLI spec §3.5 `speca browse [glob]`)

```
/runs/<id>/findings?glob=contracts/**/*.sol
```

Expands internally to `?q=path:<glob>` so it AND-combines with any
existing DSL filter.

### Markdown export (CLI spec §3.1)

The **Export Markdown** button on the findings list generates a
severity-bucketed Markdown report. Embedded backticks are wrapped in
dynamic fences; CRLF is normalised to LF.

## Chat panel

### Multi-runtime (CLI spec issue #3)

Five backends: `claude` (default) / `codex` / `gemini` / `ollama` /
`copilot`. See [Multi-runtime backends](./multi-runtime.md).

### Ask Claude about this finding (CLI spec §3.1.6)

The button on the finding detail opens the chat panel pre-filled with
the finding's context (severity / verdict / file::line /
evidence_snippet / …).

### Context cap (CLI spec §8.5)

The prefilled context block is truncated to **50 KB** (TextEncoder
byte-accurate, multi-byte safe). Over-cap context is replaced with a
trailing `…(context truncated to 50 KB budget…)` marker.

### Approval gate (three layers)

Side-effect tools that the chat can fire (`launch_pipeline` /
`stop_pipeline`) are guarded three ways:

1. SDK `tools=` argument is the read-only allowlist
2. Stream-side re-check on each `tool_use` (out-of-allowlist names
   emit `tool_not_allowed` and terminate)
3. Front-end `<ToolCard>` type guard

## UX / settings

### Themes (CLI spec §10.5)

`light` / `dark` / `system` / **`solarized`**. Solarized uses Ethan
Schoonover's canonical palette layered on the Nyx tokens. Prism syntax
highlighting tracks the theme.

### i18n

Full EN / JA via i18next. Toggle from the header.

### Diagnostics (`/diagnostics`)

The `speca doctor` equivalent. Probes Node / uv / git / claude / gh /
VSCode CLI versions, auth state, and MCP server connectivity.

## Error handling

### 7-case error modal (CLI spec §10.4)

Backend launch errors (`clone_failed`, `invalid_target_repo`,
`ref_not_found`, `worktree_failed`, `anthropic_unreachable`,
`run_not_found`, `still_running`, `invalid_phases`,
`invalid_workspace_input`) render in `ErrorModal` with i18n title /
body / suggested action. Retry / Close, plus a "Show technical details"
disclosure for the raw envelope.

## Init config persistence (CLI spec §3.1 `speca init`)

Creating a new run writes
`outputs/<run_id>/TARGET_INFO.json` and `BUG_BOUNTY_SCOPE.json` from
the wizard inputs immediately. Phases 0a / 0c overwrite them later, but
the initial stub matches `speca init` and is inspectable by external
tooling.

## Keyboard shortcuts (full list, CLI spec §10.3)

| Key | Scope | Action |
| --- | --- | --- |
| `?` | global | Help modal |
| `Esc` | global | Close any open modal / chat |
| `c` | global | Toggle chat |
| `g r` | global | `/runs` |
| `g s` | global | `/settings` |
| `g d` | global | `/diagnostics` |
| `/` | findings | Focus filter |
| `j` / `k` | findings | Next / previous row |
| `Enter` / `Space` | phase row | Expand |
| `l` | phase row | Expand + scroll log |
| `f` | phase row | Force re-run |

All shortcuts are IME-safe (suppressed during composition).

## Mobile

≤720px: header wraps, runs table scrolls horizontally, findings list
stacks vertically.

## Architecture summary

```
Browser
   │  WebSocket + REST
   ▼
FastAPI (web/server/)
   │  subprocess
   ▼
scripts/run_phase.py ─── ClaudeRunner / APIRunner / CodexAPIRunner ...
                                                │
                                                ▼
                                          Each LLM API
```

See [UI_DESIGN.md](https://github.com/NyxFoundation/speca/blob/dev/docs/UI_DESIGN.md)
for the slice diagrams + full API surface.
