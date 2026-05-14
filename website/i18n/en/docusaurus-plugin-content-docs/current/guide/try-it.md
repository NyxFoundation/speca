---
sidebar_position: 3
---

# Try it out

You can drive SPECA from the **CLI**, the **Web UI**, or any of the
**multi-runtime backends** (Codex / Gemini / Ollama / Copilot in
addition to Claude). The Web UI is the easiest first run — it bundles
the runtime picker and the run wizard, plus per-error guidance.

Each step lists "what to check if it fails" inline.

## Prerequisites

| Item | Required |
|---|---|
| Node.js | ≥ 20 |
| Python | 3.12 (we recommend `uv`) |
| git | any |
| OS | Windows 11 / macOS 14 / Ubuntu 22.04 verified |
| Auth | one of: claude.ai subscription (Pro/Max) / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` / Ollama (self-hosted is free) |

Sanity-check:

```bash
node --version    # v20+
uv --version      # 0.6+
git --version
```

---

## Route A — Drive an audit from the Web UI (recommended)

### 1. Clone + install deps

```bash
git clone https://github.com/NyxFoundation/speca.git
cd speca

uv sync                          # Python deps
cd web/frontend && npm install   # Frontend deps
cd ../..
```

**If something breaks:**
- `uv sync` errors → confirm `python -V` reports 3.12; otherwise
  `uv python install 3.12`
- `npm install` errors → `node -v` below v20? `nvm install 20 && nvm use 20`
- Windows + bash-style `&&` not working → PowerShell uses
  `cd web\frontend; npm install; cd ..\..`

### 2. Log into Claude (the supported default)

```bash
npm install -g @anthropic-ai/claude-code
claude auth login        # opens claude.ai OAuth in the browser
```

**Check:**

```bash
claude auth status --json
# → { "loggedIn": true, "authMethod": "claude.ai", "email": "...", "subscriptionType": "max" }
```

**Or pick a different auth source:**

```bash
# Anthropic API key (no subscription)
export ANTHROPIC_API_KEY=sk-ant-api-...

# Or OpenAI / Gemini / Ollama (multi-runtime)
export OPENAI_API_KEY=sk-...
export GEMINI_API_KEY=...
ollama serve   # in another terminal for self-hosted Ollama
```

### 3. Start the Web server

```bash
uv run speca-web --port 7411 --host 127.0.0.1 --serve-frontend
```

Expected log:

```
INFO:     Started server process [...]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:7411
```

Open http://127.0.0.1:7411/ in a browser:

![Dashboard](/img/web-ui/01_dashboard_default.png)

**If something breaks:**
- Port in use → `--port 8000` etc.
- `claude auth status` passes but Web UI shows `logged_in: false` →
  credentials path mismatch. Check
  `ls ~/.claude/.credentials.json` (note the leading dot)
- Browser cannot connect → firewall. `--host 0.0.0.0` to expose, or
  check loopback with `127.0.0.1`

### 4. (Optional) Try a different runtime

`/settings` exposes a **Chat runtime** section:

![Runtime selector](/img/web-ui/11_runtime_selector.png)

- **Claude** → default, no extra setup
- **Codex** → export `OPENAI_API_KEY` first
- **Gemini** → export `GEMINI_API_KEY`
- **Ollama** → self-hosted (`OLLAMA_HOST=http://localhost:11434`) or
  cloud (`OLLAMA_HOST=https://ollama.com` + `OLLAMA_API_KEY`)
- **Copilot** → `gh auth login` + Copilot subscription (chat only, no audit)

See [Multi-runtime backends](../operations/multi-runtime.md) for the
deep dive.

### 5. Start an audit run

Dashboard → **+ New run** → either **Picker** or **Wizard**.

**Wizard mode** (`/runs/new/wizard`):

1. **Project type** — `smart_contract` / `web_app` / `library` / `other`
2. **Target repo** — `owner/name` (e.g. `OpenZeppelin/openzeppelin-contracts`)
3. **Target ref** — empty for default branch, or `v5.0.0` etc.
4. **Scope** — Bug bounty URL if any, otherwise leave empty
5. **Spec URLs** — optional (Phase 01a seed)
6. **Confirm** — Launch

**Failure cases:**

| Error | Meaning | Manual fix |
|---|---|---|
| `clone_failed` | private repo / typo / network | `git ls-remote https://github.com/<owner>/<name>` to verify reachability. For private repos export `GH_TOKEN` then restart |
| `invalid_target_repo` | slug format invalid | Use plain `owner/name`. No `https://` prefix |
| `ref_not_found` | branch/tag missing on origin | `git ls-remote --tags --heads <repo>` to confirm |
| `worktree_failed` | `.speca/workspaces/` corruption | `rm -rf .speca/workspaces/<target>` to regenerate |
| `anthropic_unreachable` | API outage / auth expired | Re-check `claude auth status --json`, see status.anthropic.com |

Errors render in a localised modal with suggested action (CLI spec
§10.4 — 7 cases covered).

### 6. Watch the run

![Run detail with phases](/img/web-ui/05_run_detail_budget_phases.png)

Click each phase to expand, or Tab-focus a row and press `l` to open
the log pane. `f` force re-runs one phase.

**Budget exceeded:** click the gauge to open the cap-bump modal:

![Cap-bump modal](/img/web-ui/06_budget_cap_bump_modal.png)

### 7. Browse findings

![Findings list](/img/web-ui/03_findings_list.png)

Filter via DSL:

```
severity:HIGH|CRITICAL verdict:CONFIRMED_VULNERABILITY path:contracts/**/*.sol
```

Or deep-link with `?glob=`:

```
http://127.0.0.1:7411/runs/<id>/findings?glob=contracts/**/*.sol
```

Row click → detail page with Prism code highlighting:

![Finding detail](/img/web-ui/04_finding_detail_code_highlight.png)

"Ask Claude about this finding" injects the finding into the chat
panel as context.

### 8. (Optional) Markdown export

The **Export Markdown** button on the findings list produces a
severity-bucketed one-file report. Good starter material for a bug
bounty submission or internal review.

---

## Route B — CLI only (CI / scripts)

```bash
# Same clone + uv sync as before
export KEYWORDS="ethereum execution client"
export SPEC_URLS="https://ethereum.github.io/execution-specs/src/"

uv run python scripts/run_phase.py --target 04 --workers 4
```

Outputs land in `outputs/`. Resume is automatic (reads processed IDs
from `<phase>_PARTIAL_*.json`) — Ctrl-C and rerun and you pick up
where you left off.

### Pick a runtime

```bash
# What's available?
uv run python scripts/run_phase.py --list-runtimes

# Drive the audit via OpenRouter
export API_RUNNER_API_KEY=sk-or-v1-...
uv run python scripts/run_phase.py --target 04 --runtime api --workers 4

# JSON event stream for CI / speca-cli
uv run python scripts/run_phase.py --target 04 --runtime api --json | tee pipeline.ndjson
```

See [Multi-runtime backends](../operations/multi-runtime.md).

### Recovery

```bash
# Force re-run a failed phase
uv run python scripts/run_phase.py --phase 03 --force --workers 4

# Skip a phase (e.g. 02c when MCP isn't available)
uv run python scripts/run_phase.py --phase 01a 01b 01e 03 04 --workers 4

# Inspect cleanup before forcing
uv run python scripts/run_phase.py --phase 03 --cleanup-dry-run
```

See [Troubleshooting](../operations/troubleshooting.md) for the long
list.

---

## Reading the CLI TUI

```
SPECA · openzeppelin-ownable-walkthrough          cost: $1.42 / $50 budget
─────────────────────────────────────────────────────────────────────────
01a Spec Discovery     ████████████████████  done   23 sections   $0.18
01b Subgraph Extract   ████████████████████  done   12 subgraphs  $0.24
01e Property Gen       ████████████████████  done   18 props      $0.31
02c Code Resolution    ████████░░░░░░░░░░░░  3 / 18 workers=4    $0.21
03 Audit Map           ░░░░░░░░░░░░░░░░░░░░  pending             —
04 Review              ░░░░░░░░░░░░░░░░░░░░  pending             —
```

Phase semantics → [Pipeline overview](../pipeline/overview.md).

---

## Cost & wall-time estimates

| Codebase | Wall time | Cost (Sonnet 4.5) |
|---|---|---|
| Small contract (~1K LoC) | 5–10 min | $1–5 |
| Mid-size repo (~50K LoC) | 15–40 min | $20–50 |
| Production client (~500K LoC) | 1–3 hours | $50–100 |

| Runtime | Relative cost | Speed | Audit accuracy |
|---|---|---|---|
| Claude (Sonnet 4.5) | baseline | baseline | ★★★ |
| Claude Pro/Max OAuth | 0 (subscription) | baseline | ★★★ |
| Codex (GPT-4o) | ≈0.5x | baseline | ★★☆ |
| Gemini (2.0 Flash) | ≈0.3x | ★1.5x faster | ★★☆ |
| Ollama (self-hosted llama3.2:70b) | 0 (local) | ★0.3x slower | ★☆☆ |

Cost discussion → [Model selection design notes](../design-notes/model-benchmark-takeaways.md).

---

## Quick troubleshooting

Long-form on the **[Troubleshooting](../operations/troubleshooting.md)**
page. Quick "try this first":

### Phase 01a "Empty results"

`outputs/BUG_BOUNTY_SCOPE.json` missing / `in_scope` empty. Re-run the
wizard or hand-edit it. Format in [config files](../getting-started/config-files.md).

### Exit code 64 / 65

- **64** — `--budget` reached → raise it or narrow scope
- **65** — circuit breaker → check `outputs/logs/<phase>_*.jsonl`

### Chat panel produces no reply

1. `signed in as ...` visible in the header?
2. `/diagnostics` shows claude / codex / gemini CLI availability?
3. Try a different runtime in Settings (claude → ollama)

### Web UI does not render

```bash
curl http://127.0.0.1:7411/api/health
# {"status":"ok"} → API up; frontend cache issue
```

Hard-refresh with Ctrl+Shift+R.

---

## After your first audit

Open `speca browse` (CLI) or `/runs/<id>/findings` (Web). You'll
typically ask:

- **Which are real?** Start with
  `--severity High --filter "verdict:CONFIRMED_*"`. Verdict meanings:
  [3-gate review](../concepts/gate-review.md).
- **Why was X dismissed?** `DISPUTED_FP` records which gate rejected
  it. Expand the row in `browse` with `Enter`.
- **Which proof step failed?** `speca ask <property_id>` opens a chat
  session preloaded with the finding.
- **Can I trace back to a real spec sentence?** Yes — every finding
  links back to its spec source. The chain is illustrated in the
  [worked example](../concepts/worked-example.md).

---

## Next steps

- [CLI reference](../getting-started/cli-reference.md) — every flag + `--runtime`
- [Web UI features](../operations/web-ui-features.md) — every screen
- [Multi-runtime backends](../operations/multi-runtime.md) — Codex / Gemini / Ollama / Copilot
- [Troubleshooting](../operations/troubleshooting.md) — manual recovery
- [Pipeline overview](../pipeline/overview.md) — per-phase semantics
- [Concepts / Spec-driven](../concepts/spec-driven.md) — why this design works
