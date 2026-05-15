---
sidebar_position: 5
---

# Web UI

SPECA is CLI-first, but ships with `speca-web` so you can drive the
pipeline from a browser. The positioning is strictly **CLI Client** —
the same operations you would run via `scripts/run_phase.py` or
`speca-cli` ([issue #3](https://github.com/NyxFoundation/speca/issues/3)),
surfaced as web pages.

![SPECA dashboard](/img/web-ui/01_dashboard_default.png)

## What you can do

- Browse past audit runs and inspect their detail
- Watch phase progress live over WebSocket
- Filter / sort / Markdown-export findings
- Kick off a new audit from the picker or guided wizard
- Chat with **Claude / Codex / Gemini / Ollama / Copilot** from the right-rail panel (switchable in Settings)
- Switch runtime / theme (light/dark/system/**solarized**) / language (EN/JA) from Settings

For the full feature list see [Web UI features](../operations/web-ui-features.md);
for runtime switching see [Multi-runtime backends](../operations/multi-runtime.md).

## Launching

```bash
uv run speca-web --port 7411 --host 127.0.0.1 --serve-frontend
```

Open `http://127.0.0.1:7411/`. If `claude auth status` reports
`logged_in=true`, you land directly on the dashboard; otherwise the
login screen offers a paste-code OAuth flow and an API-key form:

![Login screen with paste-code OAuth](/img/web-ui/10_login_paste_code.png)

## Localhost only by default

The server binds `127.0.0.1` by default. To expose it on a LAN, pass
`--host 0.0.0.0` explicitly — and only in environments where firewall /
NAT protection is in place.

## Run detail — phase progress + budget gauge

![Run detail with phase rows and budget gauge](/img/web-ui/05_run_detail_budget_phases.png)

Phase rows are collapsible. With one focused, `l` scrolls the log
pane into view and `f` force re-runs just that phase. Clicking the
budget gauge opens a **cap-bump modal** that raises / clears
`max_budget_usd`:

![Budget cap-bump modal](/img/web-ui/06_budget_cap_bump_modal.png)

## Findings — DSL filter + code highlighting

The findings list filters server-side by severity / verdict / phase
chips and layers a richer client-side DSL on top (path globs, etc.).
Markdown export is one click:

![Findings list](/img/web-ui/03_findings_list.png)

Clicking a row opens the detail page with the `evidence_snippet`
highlighted by Prism (Solidity / TS / JS / Python / Rust / Go / Java /
C / C++):

![Finding detail with code highlight](/img/web-ui/04_finding_detail_code_highlight.png)

## Chat panel — multi-runtime

Click **Chat** in the header (or press `c`) to open the right-rail
chat panel:

![Chat panel](/img/web-ui/07_chat_panel_empty.png)

The backend that drives the conversation is chosen in Settings — five
backends are available: **Claude / Codex / Gemini / Ollama / Copilot**.
See [Multi-runtime backends](../operations/multi-runtime.md) for the
full story.

## Settings — runtime / theme / language

![Runtime selector in Settings](/img/web-ui/11_runtime_selector.png)

The **Chat runtime** section is a 5-way switch with availability
badges (`✓` / `!`) so you can see at a glance which backend is ready
to go. Expand Advanced to override the model or Ollama host per
runtime.

Theme: light / dark / system + **Solarized**:

| Default | Solarized |
| --- | --- |
| ![dashboard default](/img/web-ui/01_dashboard_default.png) | ![dashboard solarized](/img/web-ui/02_solarized_dashboard.png) |

Toggle from the header `L D A S` buttons:

![Theme toggle 4 buttons](/img/web-ui/09_settings_theme_4buttons.png)

## Keyboard shortcuts

`?` always opens the cheat sheet:

![Keyboard shortcuts help](/img/web-ui/08_keyboard_shortcuts_help.png)

| Key | Action |
| --- | --- |
| `?` | Keyboard-shortcut help modal |
| `Esc` | Close any open modal / chat panel |
| `c` | Toggle chat panel |
| `g r` / `g s` / `g d` | Navigate to Runs / Settings / Diagnostics |
| `/` | Focus findings filter |
| `j` / `k` | Move to next / previous finding row |
| Phase row focus + `l` / `f` | Expand log / force re-run that phase |

All shortcuts are IME-safe (suppressed during composition).

## Architecture

- **Backend** — FastAPI + uvicorn (`web/server/`). Runs `scripts/run_phase.py`
  as a subprocess; never imports orchestrator Python code directly.
- **Frontend** — React 19 + TypeScript + Vite (`web/frontend/`).
  TanStack Query for REST + WebSocket, Zustand for UI state, i18next
  for EN/JA.
- **State** — `.speca/runs/<run_id>/state.json` for run state,
  `~/.speca/chat/<conversation_id>.json` for chat history,
  `~/.speca/runtime.json` for runtime preferences. No secrets in any
  of these.

## See also

- [Getting started / Installation](../getting-started/installation.md)
- [Web UI features (everything)](../operations/web-ui-features.md)
- [Multi-runtime backends](../operations/multi-runtime.md)
