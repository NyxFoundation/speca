---
sidebar_position: 12
---

# Troubleshooting (manual recovery)

When the pipeline / Web UI / multi-runtime path gets stuck, this page is
the manual-recovery cheat sheet. The goal is to make it obvious *which
log, state file, or env var to inspect — and what to edit to come back
to a healthy state*.

:::tip Order of inspection
1. Last 50 lines of `uv run speca-web` or the CLI **stderr**
2. Tail of the latest `outputs/logs/<phase>_*.jsonl`
3. `.speca/runs/<run_id>/state.json` for the supervisor's view
4. `outputs/<phase>_PARTIAL_*.json` for what is already saved

90% of problems get diagnosed from those four.
:::

---

## A. Setup

### `uv sync` fails

```text
error: Could not find Python 3.12 ...
```

```bash
uv python install 3.12
uv sync
```

Still stuck? Nuke the venv and retry:

```bash
rm -rf .venv
uv sync
```

### `npm install` (web/frontend) hangs

Usually a Node version mismatch.

```bash
node -v        # must be v20+
npm cache clean --force
rm -rf web/frontend/node_modules web/frontend/package-lock.json
cd web/frontend && npm install
```

### `claude` / `codex` / `gemini` / `gh` CLI not found

Check PATH:

```bash
where claude   # Windows
which claude   # macOS / Linux
```

Add to PATH (example `~/.bashrc` / `~/.zshrc`):

```bash
export PATH="$HOME/.npm-global/bin:$PATH"
```

---

## B. Authentication

### Web UI stays on the login screen even though `claude auth status` is OK

**Cause:** credentials path mismatch. SPECA reads
`~/.claude/.credentials.json` (**leading dot**) as the primary source
and `~/.claude/credentials.json` (no dot) as a legacy fallback.

**Check:**

```bash
ls -la ~/.claude/.credentials.json
cat ~/.claude/.credentials.json | head -c 80   # expect a `claudeAiOauth` field
```

**Manual fix:**

```bash
claude auth logout
claude auth login
```

Or paste an API key directly:

```bash
# Either in the Web UI login form, or:
echo '{"apiKey":"sk-ant-..."}' > ~/.claude/credentials.json
```

### Chat panel gets 429 (rate-limited)

**Cause:** A claude.ai OAuth token forwarded to the Anthropic SDK as an
API key hits the subscription throttle.

**Manual fix:** With PR #63 merged, the server auto-falls back to the
`claude` CLI subprocess for OAuth tokens. If you still see 429:

```bash
# 1. Other concurrent claude processes can share the subscription quota
ps -ef | grep claude        # macOS / Linux
tasklist | findstr claude   # Windows

# 2. Re-login if SPECA is seeing stale creds
claude auth logout && claude auth login

# 3. Switch runtime via Settings (Ollama / Codex)
```

### Codex / Gemini env vars are ignored

```bash
echo $OPENAI_API_KEY
echo $GEMINI_API_KEY
```

Env set after the Web server started → restart the server. PowerShell:

```powershell
$env:OPENAI_API_KEY = "sk-..."
uv run speca-web --port 7411 --serve-frontend
```

---

## C. Pipeline runs

### Phase 01a returns "Empty results"

**Cause:** `outputs/BUG_BOUNTY_SCOPE.json` missing or `in_scope` empty.

```bash
cat outputs/BUG_BOUNTY_SCOPE.json
```

Expected:

```json
{
  "url": "https://example.com/bug-bounty",
  "in_scope_assets": ["contracts/MyContract.sol"],
  "spec_urls": ["https://example.com/spec.html"]
}
```

**Manual fix:** Re-run the Web UI wizard, hand-edit the file, or rerun
with explicit env:

```bash
export SPEC_URLS="https://geth.ethereum.org/docs"
uv run python scripts/run_phase.py --phase 01a --force
```

### Phase 02c MCP tree-sitter error

**Symptom:** `mcp__tree_sitter__get_symbols` fails, `code_scope` is
mostly empty.

**Cause:** MCP server not registered or runtime is not claude (only
ClaudeRunner drives MCP today).

```bash
bash scripts/setup_mcp.sh --verify
bash scripts/setup_mcp.sh             # re-register if needed
```

Split-run workaround:

```bash
# 02c with claude:
ORCHESTRATOR_RUNNER=claude uv run python scripts/run_phase.py --phase 02c --force

# Rest with another runtime:
uv run python scripts/run_phase.py --phase 03 04 --runtime api --force
```

### Phase 03 / 04 all batches fail

**Symptom:** circuit-breaker tripped (exit 65), every batch retry
exhausted.

```bash
ls -t outputs/logs/03_*.jsonl | head -3
tail -50 outputs/logs/03_W0B0_<latest>.jsonl
```

Look for `tool_use` loops, Anthropic API timeouts, overload errors.

**Manual fixes:**

```bash
# 1. Transient API issue — resume with lower concurrency
uv run python scripts/run_phase.py --phase 03 --force --workers 2 --max-concurrent 4

# 2. Regen queues (prompt-derived hang)
rm outputs/03_QUEUE_*.json
uv run python scripts/run_phase.py --phase 03 --force

# 3. Delete one broken PARTIAL, keep the rest, resume
rm outputs/03_PARTIAL_W0B5_*.json
uv run python scripts/run_phase.py --phase 03
```

### Phase 03 exits with "BUG_BOUNTY_SCOPE.json missing"

Phase 01e requires it. Minimal valid content:

```json
{
  "url": null,
  "in_scope_assets": ["src/**/*.sol"],
  "spec_urls": []
}
```

---

## D. Run state

### `/api/runs/<id>` returns 404 (state.json exists)

**Cause:** state.json without a sibling manifest.json (cancel before
finalize). Fixed in PR #62, which falls back to state.json.

```bash
ls .speca/runs/
ls .speca/runs/<id>/
cat .speca/runs/<id>/state.json | python -m json.tool
```

If `run_id` inside state.json mismatches the directory:

```bash
python -c "
import json
from pathlib import Path
p = Path('.speca/runs/<id>/state.json')
d = json.loads(p.read_text())
d['run_id'] = '<id>'
p.write_text(json.dumps(d, indent=2))
"
```

### Clean up "orphaned running" runs

```bash
python -c "
import json
from pathlib import Path
for p in Path('.speca/runs').glob('*/state.json'):
    d = json.loads(p.read_text())
    print(p.parent.name, d.get('status'), d.get('owner_pid'))
"
```

`owner_pid` not present → orphan. A Web server restart auto-relabels
to `crashed`. To do it manually:

```bash
python -c "
import json
from pathlib import Path
for p in Path('.speca/runs').glob('*/state.json'):
    d = json.loads(p.read_text())
    if d.get('status') == 'running':
        d['status'] = 'crashed'
        d['cancel_requested'] = True
        p.write_text(json.dumps(d, indent=2))
"
```

### `.speca/workspaces/` is huge

```bash
du -sh .speca/workspaces/*
rm -rf .speca/workspaces/<target_slug>
# regenerated on next run
```

---

## E. Web UI

### Settings runtime switch has no effect

```bash
curl http://127.0.0.1:7411/api/runtime
cat ~/.speca/runtime.json
```

Both should agree. Validate by issuing a direct SSE turn:

```bash
CID=$(python -c "import uuid; print(uuid.uuid4())")
curl -N -X POST http://127.0.0.1:7411/api/chat/conversations/$CID/messages \
  -H "Content-Type: application/json" \
  -d '{"text":"hello"}'
```

Manual override:

```bash
cat > ~/.speca/runtime.json <<'EOF'
{
  "runtime": "ollama",
  "ollama_host": "http://localhost:11434",
  "ollama_model": "llama3.2"
}
EOF
```

### Chat SSE renders nothing (Network tab shows bytes)

**Cause (fixed in PR #62):** Windows sse-starlette emits `\r\n\r\n`
frame terminators; the SPA parser only split on `\n\n`.

```bash
CID=$(python -c "import uuid; print(uuid.uuid4())")
curl -N -X POST http://127.0.0.1:7411/api/chat/conversations/$CID/messages \
  -H "Content-Type: application/json" \
  -d '{"text":"hi"}' | xxd | head -10
```

If you see `0d 0a 0d 0a` separators, ensure
`web/frontend/src/features/chat/useChatStream.ts` normalises CRLF →
LF:

```typescript
buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
```

### Chat history disappeared

```bash
ls ~/.speca/chat/ 2>/dev/null || ls .speca/chat/
```

Plain JSON — recover or hand-write:

```json
{
  "conversation_id": "...",
  "messages": [
    {"role":"user","content":[{"type":"text","text":"..."}],"timestamp":"2026-05-15T..."},
    {"role":"assistant","content":[{"type":"text","text":"..."}],"timestamp":"2026-05-15T..."}
  ],
  "created_at": "...",
  "last_message_at": "..."
}
```

---

## F. Multi-runtime

### `--runtime codex` exits 2

```text
ERROR: runtime 'codex' cannot drive the orchestrator.
```

Until PR #67 merges, codex / gemini / ollama are orchestrator-side
stubs. Use `api` against the same provider in the meantime:

```bash
export API_RUNNER_API_KEY=$OPENAI_API_KEY
export API_RUNNER_BASE_URL=https://api.openai.com/v1
export API_RUNNER_MODEL=gpt-4o
uv run python scripts/run_phase.py --target 04 --runtime api
```

### Ollama self-hosted not responding

```bash
curl http://localhost:11434/api/tags
# Should list pulled models.
```

If not:

```bash
ollama serve &
ollama pull llama3.2
```

OpenAI-compatible endpoint sanity-check:

```bash
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2","messages":[{"role":"user","content":"hi"}]}'
```

---

## G. Archive / reproducibility

### Inspect `.speca/runs/<id>/`

```bash
tree .speca/runs/<id>/
cat .speca/runs/<id>/manifest.json | python -m json.tool
ls .speca/runs/<id>/phases/
```

`manifest.json` carries commit SHA, env snapshot, spec sources, and
runtime — that's all you need to reproduce on another machine.

### Reproduce a past run elsewhere

```bash
# 1. Tarball
tar czf run-<id>.tar.gz .speca/runs/<id>/ outputs/<id>/

# 2. On the other host
tar xzf run-<id>.tar.gz

# 3. Replay env_snapshot
python -c "
import json
m = json.load(open('.speca/runs/<id>/manifest.json'))
for k, v in m['env_snapshot'].items():
    print(f'export {k}={v}')
"

# 4. Same commit + runtime
git checkout <sha>
ORCHESTRATOR_RUNNER=<runtime> uv run python scripts/run_phase.py --phase 03 04 --force
```

---

## H. Nuclear option

When nothing else works:

```bash
# 1. Wipe state
rm -rf .speca/ ~/.speca/
rm -rf outputs/

# 2. Reset credentials
rm ~/.claude/.credentials.json ~/.claude/credentials.json 2>/dev/null
claude auth login

# 3. Reinstall deps
rm -rf .venv web/frontend/node_modules
uv sync
cd web/frontend && npm install && cd ../..
```

If that still fails, open an issue at
[NyxFoundation/speca/issues](https://github.com/NyxFoundation/speca/issues)
with a reproducer.

## Log / state file map

| Path | Contents |
|---|---|
| `outputs/logs/<phase>_W<W>B<B>_<ts>.jsonl` | claude CLI / APIRunner stream-json log: tool_use history, cost, errors |
| `outputs/<phase>_PARTIAL_W<W>B<B>_<ts>.json` | Per-batch results (resume input) |
| `outputs/<phase>_QUEUE_<worker>.json` | Per-worker queue |
| `.speca/runs/<id>/state.json` | Supervisor's run state (status / owner_pid / phases / cancel_requested / max_budget_usd) |
| `.speca/runs/<id>/manifest.json` | Immutable run metadata (commit SHA / env snapshot / spec sources / runtime) |
| `.speca/workspaces/<target_slug>/` | Bare cache + worktree for the target |
| `~/.speca/runtime.json` | Web UI runtime preference |
| `~/.speca/chat/<conversation_id>.json` | Chat history |
| `~/.claude/.credentials.json` | claude CLI OAuth tokens (secret) |
| `~/.claude/credentials.json` | Legacy API-key location |
