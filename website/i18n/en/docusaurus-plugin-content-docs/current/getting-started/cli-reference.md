---
sidebar_position: 3
---

# CLI reference

Reference for every `speca` subcommand. Also available at runtime with `speca <subcommand> --help`.

## `speca doctor`

Validates the local environment.

```bash
speca doctor
```

Checks Node.js version, Python (`uv`) availability, Claude Code authentication, and registered MCP servers (`fetch`, `tree_sitter`). Prints the exact remediation line for any failure.

## `speca auth login` · `speca auth status`

Manages Claude API credentials.

```bash
speca auth login          # interactive: API key or claude-session
speca auth status         # show currently active credentials source
```

Credentials are stored under `~/.config/speca/auth.json`. `ANTHROPIC_API_KEY` in the environment also works.

## `speca init`

Generates `outputs/TARGET_INFO.json` and `outputs/BUG_BOUNTY_SCOPE.json` — the two files that drive the entire pipeline.

```bash
speca init
```

Flags (all optional; missing values are prompted for):

| Flag | Description |
|---|---|
| `--project-name <name>` | Project name (default: cwd basename) |
| `--target-repo <url>` | Target repository URL |
| `--target-commit <ref>` | Commit / branch / tag (default: HEAD) |
| `--target-language <lang>` | Solidity / Rust / Go / Nim / TypeScript / C / C++ / … |
| `--target-layer <layer>` | consensus / execution / application / library / … |
| `--rubric <mode>` | `default` (ethereum.org rubric) or `custom` |
| `--output-dir <dir>` | Output directory (default `$SPECA_OUTPUT_DIR` or `./outputs/`) |
| `--force`, `--yes` | Overwrite existing files without asking |
| `--non-interactive` | Refuse to prompt; require all values via flags |

For the JSON schemas see [Configuration files](./config-files.md).

## `speca run`

Executes the pipeline. Streams a TUI dashboard by default.

```bash
speca run --target 04 --workers 4
speca run --phase 01a 01b 01e
speca run --phase 03 --force --json
```

Flags:

| Flag | Description |
|---|---|
| `--phase <id…>` | Run one or more phases by ID (e.g. `--phase 01a 01b`) |
| `--target <id>` | Run all dependencies up through `<id>` |
| `--workers <N>` | Worker count per phase (default 4) |
| `--max-concurrent <N>` | Max parallel Claude invocations (default 8) |
| `--force` | Ignore resume state and re-run everything |
| `--budget <usd>` | Cost cap forwarded to the orchestrator |
| `--output-dir <path>` | Output directory (sets `SPECA_OUTPUT_DIR`) |
| `--no-tui` | Plain-text pass-through (CI-friendly) |
| `--json` | Raw NDJSON event stream on stdout |
| `--runtime <name>` | Select the execution backend (`claude` / `api` / `codex` / `gemini` / `ollama` / `copilot`) |
| `--list-runtimes` | Print the registered runtimes with availability and exit |
| `--01a-scope <mode>` | Filter Phase 01a state (`all` / `primary` / `primary+1hop` / `<N>`) |

Resume is automatic: items recorded in any `<phase>_PARTIAL_*.json` are skipped. Use `--force` to override. The pipeline can be interrupted with `Ctrl-C` and re-run safely.

### Runtime selection

`--runtime` switches the agentic backend driving the pipeline. See
[Multi-runtime backends](../operations/multi-runtime.md) for per-backend
setup, env vars, and known limits.

```bash
# List registered runtimes with availability
speca run --list-runtimes

# JSON for CI / speca-cli consumers
speca run --list-runtimes --json

# Drive the audit via OpenRouter
speca run --target 04 --runtime api --workers 4

# Refuses to silently fall back to claude when the runtime is a stub
speca run --target 04 --runtime copilot   # → exit code 2
```

`--runtime` overrides `ORCHESTRATOR_RUNNER`. Picking a stub runtime
aborts with exit 2 instead of silently falling back, which would
otherwise produce misleading PARTIALs.

For phase IDs see [Pipeline overview](../pipeline/overview.md).

## `speca browse`

TUI viewer for Phase 04 findings.

```bash
speca browse                                    # default glob
speca browse outputs/04_PARTIAL_*.json
speca browse --severity Critical
speca browse --filter "severity:High AND verdict:CONFIRMED_*"
```

Filter DSL:

| Token | Match |
|---|---|
| `severity:Critical` | exact severity (case-insensitive) |
| `severity:Critical,High` | comma-separated OR |
| `verdict:CONFIRMED_*` | wildcard suffix |
| `prop:PROP-6a4*` | wildcard match against `property_id` |
| `repo:lighthouse` | substring match against the source-file path |
| `text:reentrancy` | substring search in summary / proof / attack / notes |
| `... AND ...`, `... OR ...`, `NOT ...`, parentheses | boolean composition |

TUI keys: `↑/↓` (or `j/k`) move, `Enter` toggle detail, `c` code peek, `f` edit filter, `/` quick text search, `s` cycle sort, `r` reload, `q` quit.

`--no-tui` / `--json` dumps the matched findings to stdout instead.

## `speca ask`

Opens a Claude Code session pre-loaded with the context of one finding.

```bash
speca ask                                          # pick the first finding interactively
speca ask PROP-abc-001 --from outputs/04_PARTIAL_*.json
speca ask --session 9f1c2e0a-...                   # resume an earlier session
speca ask --no-tui --from finding.json --max-context 10000
```

Useful for asking *"what is the exact proof step that fails?"*, *"show me a minimal patch,"* or *"is this a real exploit path or an FP?"*

## `speca version`

Prints the CLI version (and the matching pipeline schema version).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | User-visible error (the CLI prints a remediation hint) |
| 2 | Bad invocation (unknown flag, missing required input) |
| 64 | Budget exceeded — the orchestrator hit `--budget` |
| 65 | Circuit breaker tripped — too many consecutive failures |

Codes 64 and 65 are designed to be caught by CI scripts so a runaway run doesn't burn the rest of a budget.
