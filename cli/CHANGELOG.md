# Changelog

All notable changes to `speca-cli` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`speca attach`** ([#27]) — read-only attach to a running pipeline in
  cwd. Reconstructs the phase rows from `outputs/*_PARTIAL_*.json`
  (filenames, mtimes, and real `metadata.item_count` sums — no metrics are
  invented) and tails `outputs/logs/*.log.jsonl` through the existing
  polling log watcher, so a second terminal sees the same dashboard as
  `speca run` without spawning a new orchestrator. Read-only: the stop /
  force keybindings are disabled and detaching (`q`) never signals the
  run. Exits 0 with a hint when there is nothing to attach to. `--no-tui`
  prints a scan summary + plain-text log tail; `--json` emits an
  `attach-summary` NDJSON envelope followed by `log` records.
- **M4 acceptance at full Sherlock-RQ1 scale** ([#29]) — the complete
  Phase 04 PARTIAL set of the RQ1 benchmark run (102 files / 550 reviewed
  items / 72 actionable findings across 10 Ethereum-client repos, plus
  the nethermind Phase 03 slice) is committed under
  `test/fixtures/sherlock-rq1/`. New acceptance tests pin the per-repo
  finding counts, exercise every filter atom (`severity:` / `verdict:` /
  `prop:` / `repo:` / free text) against real data, and verify windowed
  rendering + severity ordering on the 148-row prysm table. A
  non-CI-gating benchmark (`npm run perf:rq1`) reports loader / filter /
  sort / render timings over the full set.

### Fixed

- Dashboard phase rows no longer claim "0 results" for a completed phase
  whose result count is unknown (attach mode) — they render "done".

[#27]: https://github.com/NyxFoundation/speca/issues/27
[#29]: https://github.com/NyxFoundation/speca/issues/29

## [0.9.2] - 2026-06-16

Patch release on the 0.9.x soak line. Adds the `speca corpus` subcommand
suite — browse, inspect, share, and garbage-collect the per-run trace
archives written under `.speca/runs/<run-id>/` — built entirely in
TypeScript/Ink with no Python subprocess. Also de-flakes the `speca ask`
streaming render test on Windows.

### Added

- **`speca corpus <sub>` subcommand suite** ([#66], closes [#32]) —
  browse and share per-run trace archives (`.speca/runs/`):
  - `corpus list` — Ink table over every run-id under the archive root,
    sorted descending by `started_at`. Unreadable archives float to the
    bottom with a `broken` status so they stay visible rather than
    silently dropping out.
  - `corpus show <run-id>` — manifest plus per-phase summary (partials /
    logs / graphs / cost per phase) for quick provenance checks before
    deciding to export or gc.
  - `corpus export <run-id>` — redacted slice ready to share. Defaults to
    the spec-derived phases `01a,01b,01e`; the finding-bearing phases
    (`02c`/`03`/`04`) are gated behind `--unsafe-include-findings`. Ships
    a generated `README`, an env.json key allowlist
    (`KEYWORDS` / `SPEC_URLS` / `SPECA_OUTPUT_DIR` / `SPECA_01A_SCOPE` /
    `ORCHESTRATOR_RUNNER` / phases — unknown keys are dropped and listed
    under `_redacted_keys`), `manifest.notes` truncation (first line /
    120 chars, so Python tracebacks and auditor-local paths don't leak),
    and `target_info.repo_path` stripping.
  - `corpus gc --older-than <dur>` — soft-delete only (renames into
    `<root>/.trash/<run-id>-<ts>-<nonce>`, never hard-deletes), with a
    per-candidate timestamp + 6-hex nonce + `stat()` pre-check so
    concurrent / two-candidate gc can't silently overwrite. Defaults to
    `--dry-run`.
- **Corpus substrate** in `cli/src/lib/corpus/` — `paths` (CLI > env >
  `<cwd>/.speca/runs` precedence), `manifest` (zod schema +
  `deriveStatus` + `summarise`), `runs` (tolerant scan), `duration`
  (`<int><unit>` `--older-than` parser), `gc`, and a stream-JSON log
  `redact`or (drops `Read`/`Grep`/`Glob` calls under
  `target_info.repo_path` — `path.relative`-based, case-insensitive on
  Windows — while keeping `mcp__*` / `Write` / everything else).

### Fixed

- De-flaked the `speca ask` streaming-render test on Windows
  (`cli/test/ask.render.test.ts`).

### Tests

- +64 vitest cases (290 → 354): corpus export (×many), gc, manifest,
  redact, runs, paths, and duration suites, all green on the matrix.

[#32]: https://github.com/NyxFoundation/speca/issues/32
[#66]: https://github.com/NyxFoundation/speca/pull/66

## [0.9.1] - 2026-05-08

Patch release on the 0.9.x soak line. Closes the four `ErrorKind` paths
that shipped infrastructure-only in v0.9.0, syncs version mentions across
in-tree docs, and adds a post-publish smoke job to the release pipeline so
tarball / bin-shim / dependency-pinning regressions are caught on every
publish rather than the next time a user runs `npx speca-cli@latest`.

### Added

- **`speca run` pre-flight checks** ([#28]):
  - `auth-expired` — refuses to spawn when the active OAuth token is past
    its `expires_at`. API-key accounts and missing auth files are
    untouched.
  - `stale-resume` — refuses to spawn (without `--force`) when
    `outputs/TARGET_INFO.json` was rewritten meaningfully later than the
    newest `outputs/01b_PARTIAL_*.json`. 60-second grace window absorbs
    back-to-back `init` + `run`.
- **`speca browse` schema-mismatch gate** ([#28]) — exits with a
  parseable `[ERROR kind=schema-mismatch] …` line when every matched
  partial file fails loader validation, instead of dropping into a
  zero-row TUI.
- **`subprocess-crash` reporter** ([#28]) — `speca run`'s spawn-error
  handler now uses the canonical kind=subprocess-crash format on both
  headless and TUI paths.
- **`KNOWN_VERDICTS` const tuple** in `cli/src/lib/findings/types.ts` so
  call sites that hand-write a verdict literal can opt into the closed
  set via `KnownVerdict` (a typo'd verdict fails to compile).
- **`warnUnknownPhases` heads-up** in `speca run` — warns to stderr when
  `--phase` / `--target` carry an id outside `KNOWN_PHASE_IDS`. Forks
  may legitimately add phases via custom orchestrator configs, so the
  unknown id is forwarded; the warn just removes the surprise factor.
- **`cli/src/lib/errors/report.ts`** — stderr-side reporter that mirrors
  `<ErrorModal>` wording, with a parseable `kind=<kind>` token so CI
  scripts can match specific failure modes.
- **Post-publish smoke job** in `.github/workflows/release.yml` —
  spins up a clean ubuntu runner after every successful `npm publish`,
  installs the freshly-published version, and runs
  `speca version` / `speca help` / `speca doctor` plus an `npx` route
  check. Catches tarball / bin-shim / dependency-pinning regressions
  the in-tree tests can't see.
- **Git-build install path** in `cli/README.md` and root `README.md` —
  the npm route stays the recommended one, but contributors testing
  unreleased branches now have a documented `git clone && npm install
  && npm run build` recipe (plus `npm link`).

### Fixed

- All seven `ErrorKind`s defined in `cli/src/lib/errors/kinds.ts` now
  have at least one production caller. Before this release four kinds
  (auth-expired / schema-mismatch / stale-resume / subprocess-crash)
  had infrastructure but no code path firing them.

### Changed

- `speca version` / version-string mentions in docs now reflect the
  shipped `0.9.0` (was stale `1.0.0` / `M2`-era text in the root
  README).

### Tests

- +34 vitest cases (256 → 290): errors-reporter (×13), preflight
  detectors (×10), browse error-kinds (×2), run pre-flight + phase warn
  (×5), verdict closed-set (×2), `speca ask` multi-turn chain (×2,
  closes [#31]).

[#28]: https://github.com/NyxFoundation/speca/issues/28
[#31]: https://github.com/NyxFoundation/speca/issues/31

## [0.9.0] - 2026-05-07

Soft-launch release ahead of the v1.0.0 GA. All features from the M1–M7
milestones in [`docs/SPECA_CLI_SPEC.md`](../docs/SPECA_CLI_SPEC.md) §11
are included; the 0.9.0 version reserves the npm package name and
exercises the tag-driven release pipeline before we commit to v1.0.0
stability guarantees.

### Added

#### Core commands
- `speca version` — print speca-cli version
- `speca doctor` — diagnose Node / uv / git / claude-code / OAuth scope readiness
- `speca auth login` — paste-code OAuth flow against Anthropic Claude Code
- `speca auth login --api-key <key>` — fallback for users without a Claude Code subscription
- `speca auth status` — list saved accounts with token expiry
- `speca init` — `@clack/prompts` wizard that writes valid `TARGET_INFO.json` and `BUG_BOUNTY_SCOPE.json` (validated against the Pydantic-derived JSON Schemas)
- `speca run` — TUI dashboard that drives `scripts/run_phase.py --json`, with phase rows, worker badges, log pane, budget gauge, and budget-exceeded modal
- `speca browse` — finding browser with severity-coloured table, filter DSL (`severity:`, `verdict:`, `prop:`, `repo:`, `text:`, AND/OR/NOT, wildcards), sort, and code peek with syntax highlighting
- `speca ask` — chat with Claude about a finding via `claude --output-format stream-json --resume`, with 50KB context cap and project-local session persistence

#### Infrastructure
- Vendored `ex-machina-co/opencode-anthropic-auth` (MIT) for OAuth — see `docs/VENDOR.md`
- Cross-platform token store at `~/.config/speca/auth.json` (Windows: `%APPDATA%\speca\auth.json`), atomic write, chmod 0600 on POSIX
- NDJSON pipeline event emitter (`scripts/orchestrator/json_events.py`) with 7 event types
- JSON Schema export from Pydantic (`scripts/export_schemas.py`) bundled into the npm package
- Theme system (dark / light / solarized) loadable from `~/.config/speca/config.toml`
- Keybind override system via the same `config.toml`
- Generic `<ErrorModal>` covering SPEC §10.4's seven failure modes
- Common `--no-tui` and `--json` output-mode helpers (`getOutputMode`, `printNoTui`, `emitJson`)

#### Documentation
- `cli/README.md` (~350 lines) — end-user guide
- `docs/hiro/cli-quickstart.md` — Japanese quickstart for hirorogo team
- `cli/asciinema/README.md` — recording recipe for the demo cast
- `cli/docs/VENDOR.md` — vendored-code provenance tracker

### Tests
- 220 vitest cases across 24 files, all green on the matrix (ubuntu-22.04 / macOS 14 / windows-2022 × Node 20 / 22)

### Deferred to v1.1+
- Wiring the M6 polish infrastructure (theme, keybinds, ErrorModal, output-mode helpers) into the M3/M4/M5 subcommand renderers — the infrastructure ships standalone in v1.0; subcommand integration follows in v1.1
- `speca attach` (read-only attach to a running pipeline)
- Multi-finding chat context for `speca ask`
- Asciinema-recorded README demo cast (recording recipe shipped, asset to be uploaded post-release)
- Headless "start now, attach later" pipeline mode
