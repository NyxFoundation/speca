# speca-cli

> **Status:** M2 preview (`0.1.0-alpha.0`). Skeleton (M1) plus auth and project-wizard scaffolding (M2). Pipeline run / browse / chat are still on the roadmap (M3+). See the design [`docs/SPECA_CLI_SPEC.md`](../docs/SPECA_CLI_SPEC.md) and tracking [issue #3](https://github.com/NyxFoundation/speca/issues/3).

## What is speca-cli

`speca-cli` is a terminal user interface (TUI) for the [SPECA](https://github.com/NyxFoundation/speca) specification-anchored security-audit pipeline. SPECA itself is a Python orchestrator that drives the Claude Code CLI through six phases (`01a → 01b → 01e → 02c → 03 → 04`); running it today means cloning the repo, hand-editing two JSON files, and tailing JSONL logs in another terminal. `speca-cli` collapses that into one `npx` command:

- **Authenticate once** with your existing Claude Code subscription (no Anthropic API key required).
- **Configure a target** (repo + spec URLs) through guided prompts instead of raw JSON editing.
- **Watch the pipeline run** with live phase rows, log tail, and budget gauge (M3+).
- **Browse findings** sortable by severity and filterable by verdict (M4+).

The Python orchestrator under `scripts/orchestrator/` is **not rewritten** — `speca-cli` invokes it as a subprocess and parses its `--json` event stream. See [SPEC §1](../docs/SPECA_CLI_SPEC.md#1-overview).

## Quick start

```bash
# Run the doctor with no install
npx speca-cli@next doctor
```

If `doctor` reports all green you can move on to `auth login` and `init`. If something is missing it tells you exactly what to install.

## Installation

`speca-cli` ships on npm. Pick whichever style you prefer:

```bash
# Always-fresh, no global install (recommended for first-time use)
npx speca-cli@next <command>

# Pin to a specific release
npx speca-cli@0.1.0-alpha.0 <command>

# Global install
npm install -g speca-cli
speca <command>
```

### Requirements

| Tool | Version | Why | Install |
|---|---|---|---|
| **Node.js** | `>= 20.0.0` | Runtime for the CLI itself (`engines.node` in `package.json`) | https://nodejs.org/ |
| **git** | any recent | Phase 03/04 auto-clone the target repository at the pinned commit | https://git-scm.com/downloads |
| **uv** | any recent | Drives the Python orchestrator (replaces `pip`) | https://docs.astral.sh/uv/getting-started/installation/ |
| **Claude Code CLI** | `>= 2.x` (optional) | Used for the embedded "Ask Claude" pane and as a worker runtime when subscription auth is active | `npm install -g @anthropic-ai/claude-code` |

`speca doctor` checks each of these; install whatever is missing and re-run.

> **Distribution caveat.** The npm tarball does **not** bundle the Python sources. `speca-cli` either auto-clones `NyxFoundation/speca` into `~/.cache/speca/<version>/` or uses `SPECA_REPO=/path/to/your/checkout`. See [SPEC §10.2](../docs/SPECA_CLI_SPEC.md#102-bootstrapping-the-python-repo).

## Commands

The table below marks each command with the milestone in which it lands. Anything past M2 is **planned, not yet shipped**.

| Command | Milestone | Description |
|---|---|---|
| `speca version` | M1 | Print the speca-cli version |
| `speca doctor` | M1 | Check Node, uv, git, claude-code; in M2 also asserts the OAuth scope |
| `speca auth status` | M2 | Print current auth state (subscription / api-key / none) |
| `speca auth login` | M2 | Run the Claude Code OAuth paste-code flow (or fall back to API key) |
| `speca init` | M2 | New-project wizard — writes `outputs/TARGET_INFO.json` + `outputs/BUG_BOUNTY_SCOPE.json` |
| `speca run` | **M3 (planned)** | Headless pipeline run with stream-JSON events on stdout |
| `speca attach` | **M3 (planned)** | Read-only attach to a running pipeline in cwd |
| `speca browse` | **M4 (planned)** | TUI: jump straight to the finding browser |
| `speca config` | **M4+ (planned)** | Read / write a single key in the project JSON |
| `speca help` | M1 | Show usage |

Common flags (apply to every subcommand once the corresponding milestone lands; see [SPEC §6](../docs/SPECA_CLI_SPEC.md#6-command-surface)):

| Flag | Description | Default |
|---|---|---|
| `--project, -C <dir>` | Project directory (the one containing `outputs/`) | `cwd` |
| `--auth=<mode>` | `auto` / `subscription` / `api-key` | `auto` |
| `--no-tui` | Force plain-text output (CI mode) | `false` |
| `--json` | Emit machine-readable events on stdout (implies `--no-tui`) | `false` |
| `--verbose, -v` | Bump log level | `info` |

### `speca version`

Prints the npm package version (currently `0.1.0-alpha.0`).

### `speca doctor`

Runs four installation checks and one auth check (the auth check is added in M2):

| Check | Status meaning |
|---|---|
| **node** | `OK` if `process.version` is `>= v20`. `FAIL` otherwise. |
| **uv** | `OK` if `uv --version` succeeds. `FAIL` with install link otherwise. |
| **git** | `OK` if `git --version` succeeds. `FAIL` otherwise. |
| **claude** | `OK` if the Claude Code CLI is on PATH; `WARN` (not fail) if missing — the embedded chat pane needs it but the audit pipeline can run without. |
| **auth** *(M2)* | Reads `~/.config/speca/auth.json`, decodes the access-token JWT, and asserts the scope `user:sessions:claude_code` is present. Without that scope subscription quota is not billed correctly. See [SPEC §4.5.2](../docs/SPECA_CLI_SPEC.md#452-the-magic-scope-usersessionsclaude_code). |

Exit code is `0` if every required check passes, `1` otherwise.

### `speca auth login`

Two paths, picked automatically:

**1. Subscription auth (default, recommended).**

Opens the Claude Code OAuth authorize URL in your browser. After signing in on `claude.ai`, the page shows an authorization code. Copy the entire string and paste it back into the CLI prompt. Three formats are accepted by the parser (`parseCallbackInput`):

- the raw `code#state` hash form (what the page literally displays)
- the full URL with the hash
- a `code=...&state=...` query string

```text
$ speca auth login
We've opened the following URL in your browser:

  https://claude.ai/oauth/authorize?client_id=...&scope=user:sessions:claude_code...

After signing in, claude.ai will redirect you to a page that shows
a code. Paste the entire string below.

> Paste code: <paste here>

[OK] Signed in via Claude Code subscription.
     Account: alice@example.com
     Scope:   org:create_api_key user:profile user:inference
              user:sessions:claude_code user:mcp_servers user:file_upload
```

> **Why paste-code, not loopback?** Anthropic's authorize endpoint hard-codes `redirect_uri = https://platform.claude.com/oauth/code/callback`; `http://localhost:<port>` is rejected. See [SPEC §4.5.1](../docs/SPECA_CLI_SPEC.md#451-the-flow-is-paste-code-not-loopback) and pitfall #4 in [§9.3](../docs/SPECA_CLI_SPEC.md#93-pitfalls-drawn-from-the-references-above).

**2. API-key fallback.** Useful for CI or for users without a Claude Code subscription:

```bash
speca auth login --api-key
# or non-interactively:
ANTHROPIC_API_KEY=sk-ant-... speca auth login --api-key
```

Tokens are written to `~/.config/speca/auth.json` with `chmod 0o600` via an atomic tmp+rename. The structure follows [SPEC §4.5.4](../docs/SPECA_CLI_SPEC.md#454-token-storage-layout):

```json
{
  "anthropic": {
    "type":    "oauth",
    "access":  "<token>",
    "refresh": "<token>",
    "expires": 1715678400123,
    "scope":   "org:create_api_key user:profile ... user:sessions:claude_code ..."
  }
}
```

<!-- TODO: verify against final implementation — auth and init are landing in parallel branches; the exact JSON keys may shift before M2 ships. -->

### `speca auth status`

```text
$ speca auth status
[OK] Authenticated via Claude Code subscription
     Method:  oauth (user:sessions:claude_code)
     Expires: 2026-05-10T07:14:23Z (in 6d 21h)
```

If the token is missing or the `user:sessions:claude_code` scope is absent, exit code is `1` and a hint to run `speca auth login` is printed.

### `speca init`

Interactive wizard (powered by `@clack/prompts`) that builds the two JSON files SPECA needs in `outputs/`:

| Step | Prompt | Field | Validation |
|---|---|---|---|
| 1 | Project name | text | non-empty, filename-safe |
| 2 | Target git URL | URL | resolves via `git ls-remote` |
| 3 | Pin commit? | text or `default` | optional; verified via `git fetch` |
| 4 | Specification source(s) | multi-line URLs | each must respond `200` |
| 5 | Bug-bounty scope | template / paste / skip | template options: `ethereum-consensus`, `solana-validator`, `evm-defi`, `c-cpp-repo-audit`, `generic` |
| 6 | Audit budget | dollar cap | numeric, positive; default `$10` |

Outputs:

- `outputs/TARGET_INFO.json` — pins the repo + commit + language ([SPEC §7.3](../docs/SPECA_CLI_SPEC.md#73-target_infojson-wizard)).
- `outputs/BUG_BOUNTY_SCOPE.json` — trust model, severity rubric, scope rules ([SPEC §7.2](../docs/SPECA_CLI_SPEC.md#72-bug_bounty_scopejson-wizard)). Validated against the JSON Schema exported by `scripts/export_schemas.py` (the U2 upstream change).
- `.speca/session.json` — remembered Claude session id, last command, last tab.
- `.speca/prefs.json` — TUI prefs (theme, key-binding overrides). Recommended `.gitignore` entries.

`speca init` does **not** run the pipeline. After it finishes, `speca run` (M3+) will pick up the generated files.

## Typical workflow

A first-run user goes through five steps. Three of them are shipping in M2; steps 4–5 still need M3.

### 1. Install Node 20+ and run the doctor

```bash
node --version          # must be >= v20
npx speca-cli@next doctor
```

You should see:

```text
[OK] node     v20.18.1
[OK] uv       uv 0.4.20
[OK] git      git version 2.43.0
[OK] claude   2.1.87
```

Anything `[FAIL]` is printed with a one-line install hint. Install it and re-run.

### 2. Sign in

```bash
speca auth login
```

Pick subscription (default) — the OAuth flow opens your browser, you paste the code back, done. Verify with:

```bash
speca auth status
```

### 3. Initialise a project

```bash
mkdir my-audit && cd my-audit
speca init
```

Walk through the wizard. When it ends you'll have:

```text
my-audit/
├── outputs/
│   ├── TARGET_INFO.json
│   └── BUG_BOUNTY_SCOPE.json
└── .speca/
    ├── session.json
    └── prefs.json
```

### 4. Run the pipeline *(coming in M3)*

```bash
# Planned — not yet shipped in 0.1.0-alpha.0
speca run --target 04 --workers 4
```

Until M3 lands you can drive the orchestrator yourself with the existing Python entry point ([root README "Quick Start"](../README.md#quick-start)):

```bash
uv run python3 scripts/run_phase.py --target 04 --workers 4
```

### 5. Browse findings *(coming in M4)*

```bash
# Planned — not yet shipped
speca browse outputs/04_PARTIAL_*.json
```

For now read the JSON directly or use `jq`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `doctor` reports `node FAIL — v18.x (need >= v20)` | Install Node 20 LTS or newer from https://nodejs.org/. |
| `doctor` reports `uv not found on PATH` | `pip install uv` or follow https://docs.astral.sh/uv/getting-started/installation/. On Windows reopen the terminal so `PATH` is refreshed. |
| `doctor` reports `claude WARN — not found on PATH` | `npm install -g @anthropic-ai/claude-code`. Optional for the audit pipeline; required for the chat pane. |
| `auth login` opens the browser but you land on the wrong account | Open the URL in a private window, sign in to the correct Claude account, paste the code back. |
| `auth status` prints `scope missing user:sessions:claude_code` | The stored token was issued by a different OAuth client. Re-run `speca auth login` to force a fresh round trip. |
| `init` rejects a spec URL with "must respond 200" | The wizard requires every source to be reachable. Host a public copy if it's behind Notion/Confluence, or use `--skip-validation` (planned for M2.1+). |
| Windows: a hand-edited JSON file is parsed as garbage | Save as UTF-8 without BOM, LF line endings. `speca init` itself writes LF; re-running it overwrites cleanly. |
| Windows: `outputs\TARGET_INFO.json` not found from WSL2 | Run `speca` consistently from one shell. To mix, use `speca -C "$(wslpath /mnt/c/audits/my-audit)"`. |
| `npx` install fails on Windows with `EPERM` while extracting `node-pty` | Run the terminal as administrator for the first install, or set `npm_config_build_from_source=false`. See [SPEC §9.3 pitfall #2](../docs/SPECA_CLI_SPEC.md#93-pitfalls-drawn-from-the-references-above). |

If you are stuck, attach the output of `speca doctor --verbose` and `speca version` to a [new issue](https://github.com/NyxFoundation/speca/issues/new).

## Architecture

`speca-cli` is a thin Node.js + Ink layer over the existing Python orchestrator. It does **not** re-implement audit logic; every phase is still executed by `uv run python3 scripts/run_phase.py …` under the hood.

| Layer | Responsibility | Lib |
|---|---|---|
| TUI rendering | React-style components, screen routing, keybindings | [Ink 7](https://github.com/vadimdemedes/ink) |
| Argument parsing | Subcommand routing, `--flag` handling | [meow](https://github.com/sindresorhus/meow) |
| Wizard prompts | Multi-step `init` form (M2) | [@clack/prompts](https://github.com/bombshell-dev/clack) |
| Subprocess + PTY | Spawning the orchestrator and the embedded `claude` chat session (M3+/M5+) | [`node-pty`](https://github.com/microsoft/node-pty) for TTY-aware children; `child_process.spawn` for the orchestrator |
| Live log tail | Watching `outputs/logs/*.jsonl` (M3+) | [chokidar](https://github.com/paulmillr/chokidar) |
| Schema validation | Runtime validation of stream-JSON events and config files | [zod](https://github.com/colinhacks/zod) |
| OAuth | Vendored from `ex-machina-co/opencode-anthropic-auth` (MIT), see [SPEC §4.5](../docs/SPECA_CLI_SPEC.md#45-concrete-oauth-implementation-vendored) | (vendored) |

Full component diagram and the rejected alternatives (Bubble Tea, Crush, OpenTUI, blessed) are in [SPEC §8](../docs/SPECA_CLI_SPEC.md#8-architecture).

## Vendoring & licenses

`speca-cli` is MIT. A handful of files under `src/auth/` are **vendored verbatim** from `ex-machina-co/opencode-anthropic-auth` (MIT) and `sst/opencode` (MIT, pattern only) and carry the original licence header. Per-file provenance, the pinned upstream commit, and a refresh procedure are in [`cli/docs/VENDOR.md`](docs/VENDOR.md) (added with the M2 auth implementation). The full reuse table also lives in [SPEC §9.2](../docs/SPECA_CLI_SPEC.md#92-file-level-reuse-map-what-we-actually-lift).

All other dependencies (`ink`, `@clack/prompts`, `chokidar`, `zod`, `node-pty`, `meow`, `which`) are regular npm packages, not vendored.

## Contributing

We welcome PRs against this folder.

### Branch naming

- `feat/cli-<scope>` — new features (`feat/cli-skeleton-m1`, `feat/m2-auth`, ...).
- `fix/cli-<scope>` — bug fixes.
- `docs/cli-<scope>` — docs-only changes (this PR's branch is `docs/m2-user-guide`).

### Local development

```bash
cd cli
npm install
npm run dev -- doctor       # run from source via tsx
npm run dev -- version

npm run build               # compile to dist/
node dist/cli.js doctor     # run the built bundle

npm run typecheck
npm run test                # vitest run
npm run test:watch
```

### Layout

```
cli/
├── src/
│   ├── cli.tsx                # entry point + command routing
│   ├── lib/
│   │   └── checks.ts          # doctor probes (node / uv / git / claude)
│   ├── components/
│   │   └── Layout.tsx         # shared header / body / status frame
│   └── commands/
│       ├── version.tsx
│       ├── doctor.tsx
│       ├── auth.tsx           # M2
│       └── init.tsx           # M2
├── docs/
│   └── VENDOR.md              # provenance for vendored files (M2)
└── test/
    └── checks.test.ts
```

### CI matrix

`macos-14`, `ubuntu-22.04`, `windows-2022`. Every PR must keep all three green. The test suite is `vitest` plus `ink-testing-library` snapshots.

## Polish & customization

`speca-cli` ships a small polish layer that the M3+ subcommands consume — themes, keybind overrides, a generic error modal, and a non-TUI / JSON output mode. None of these change pipeline semantics; they just make the TUI tolerable on a wider range of terminals and embeddable in CI.

### Themes

Three themes ship in v1: `dark` (default), `light`, and `solarized`. Set the active theme in `~/.config/speca/config.toml` (Windows: `%APPDATA%\speca\config.toml`):

```toml
theme = "dark"   # or "light" / "solarized"
```

Unknown theme names fall back to `dark` silently — a typo will not crash the CLI. The theme controls the colour palette only; layout is identical across themes so you can switch mid-audit without re-learning the screens.

### Keybind overrides

Every interactive surface routes input through abstract action names (`exit`, `toggle-log`, `filter-mode`, ...). Override the default bindings per action in `config.toml`:

```toml
[keybinds]
exit         = ["q", "ctrl+c"]
toggle-log   = ["l"]
filter-mode  = ["/"]
focus-chat   = ["i"]
```

Each value is a list of key descriptors. A descriptor is one of:

- a single character (`"q"`, `"/"`),
- an Ink modifier name (`"escape"`, `"return"`, `"upArrow"`, `"pageDown"`, …),
- a `ctrl+<letter>` chord (`"ctrl+c"`, `"ctrl+l"`).

Actions absent from the config keep their defaults; an empty list disables the override and falls back to the default. The default map is the source of truth — see `cli/src/lib/keybinds/defaults.ts`.

### `--no-tui` / `--json`

Two flags govern non-interactive output and apply to every subcommand once that subcommand integrates them (currently a stub for M3/M4/M5):

- `--no-tui` forces line-by-line plain-text output. Implied automatically when stdout is not a TTY (CI, `tee`, pipes). Override the auto-detection with `SPECA_FORCE_TUI=1` if you really want to keep the TUI under a pipe.
- `--json` emits one JSON object per line (NDJSON) on stdout. Implies `--no-tui`. Each record carries at minimum `{ "type": "...", "ts": "<ISO8601>" }`; per-subcommand schemas are documented alongside each subcommand once it ships.

Examples (the `--json` schemas are stubbed until M3 lands):

```bash
# CI-friendly headless run
speca run --target 04 --no-tui

# NDJSON for downstream dashboards / log shipping
speca run --target 04 --json | jq -c 'select(.type == "phase-completed")'
```

### Demos

asciinema recordings of the three flagship flows (`doctor`, `init`, `browse`) live at the URLs below. Recording instructions, scenario list, and re-recording policy are in [`cli/asciinema/README.md`](asciinema/README.md).

- `speca doctor` — _`<TODO>` add asciinema URL once recorded_
- `speca init` — _`<TODO>` add asciinema URL once recorded_
- `speca browse` (M4) — _`<TODO>` add asciinema URL once M4 lands_

## License

MIT. See [`LICENSE`](../LICENSE) at the repository root.

> **Disclaimer.** SPECA (and `speca-cli` by extension) is a research artifact. Findings produced by the pipeline are *candidate* vulnerabilities and **must** be validated by a human before being reported to a vendor or bug-bounty program.
