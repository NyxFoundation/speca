---
sidebar_position: 5
---

# Web UI

SPECA is CLI-first, but ships with `speca-web` so you can drive the
pipeline from a browser. The positioning is strictly **CLI Client** —
the same operations you would run via `scripts/run_phase.py` or
`speca-cli` (issue #3), surfaced as web pages.

## What you can do

- Browse past audit runs and inspect their detail
- Watch phase progress live over WebSocket
- Filter / sort / Markdown-export findings
- Kick off a new audit from the picker or guided wizard
- Chat with Claude / Codex / Gemini / Ollama / Copilot from the right-rail panel
- Switch runtime / theme / language from Settings

For the full feature list see [Web UI features](../operations/web-ui-features.md);
for runtime switching see [Multi-runtime backends](../operations/multi-runtime.md).

## Launching

```bash
uv run speca-web --port 7411 --host 127.0.0.1 --serve-frontend
```

Open `http://127.0.0.1:7411/`. If `claude auth status` reports
`logged_in=true`, you land directly on the dashboard; otherwise the
login screen offers a paste-code OAuth flow and an API-key form.

## Localhost only by default

The server binds `127.0.0.1` by default. To expose it on a LAN, pass
`--host 0.0.0.0` explicitly — and only in environments where firewall /
NAT protection is in place.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| `?` | Keyboard-shortcut help modal |
| `Esc` | Close any open modal / chat panel |
| `c` | Toggle chat panel |
| `g r` / `g s` / `g d` | Navigate to Runs / Settings / Diagnostics |
| `/` | Focus findings filter |
| `j` / `k` | Move to next / previous finding row |
| Phase row focus + `l` / `f` | Expand log / force re-run that phase |

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
- [Web UI features](../operations/web-ui-features.md)
- [Multi-runtime backends](../operations/multi-runtime.md)
