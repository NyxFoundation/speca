# speca-cli v0.9.2

Patch release on the 0.9.x soak line.

```bash
npx speca-cli@latest doctor
```

## Highlights

- **New `speca corpus` subcommand suite.** Browse, inspect, share, and
  garbage-collect the per-run trace archives written under
  `.speca/runs/<run-id>/`. Pure TypeScript/Ink — no Python subprocess.
  Closes [#32].
  - `speca corpus list` — Ink table over every run-id under the archive
    root, sorted descending by `started_at`. Unreadable archives float to
    the bottom with a `broken` status so they stay visible instead of
    silently dropping out.
  - `speca corpus show <run-id>` — manifest plus per-phase summary
    (partials / logs / graphs / cost per phase) for quick provenance
    checks before deciding to export or gc.
  - `speca corpus export <run-id>` — a redacted slice ready to share.
    Defaults to the spec-derived phases `01a,01b,01e`; the
    finding-bearing phases (`02c`/`03`/`04`) are gated behind
    `--unsafe-include-findings`. The exporter ships a generated `README`,
    enforces an `env.json` key allowlist (unknown keys — including any
    future PAT-shaped ones — are dropped and listed under
    `_redacted_keys`), truncates `manifest.notes` to the first line / 120
    chars so Python tracebacks and auditor-local paths don't leak, and
    strips the absolute `target_info.repo_path`.
  - `speca corpus gc --older-than <dur>` — **soft-delete only** (renames
    into `<root>/.trash/<run-id>-<ts>-<nonce>`, never hard-deletes), with
    a per-candidate timestamp + 6-hex nonce + `stat()` pre-check so
    concurrent / two-candidate gc can't silently overwrite. Defaults to
    `--dry-run`.
- **Log redaction built in.** The export path runs every stream-JSON log
  through a redactor that drops `Read` / `Grep` / `Glob` calls rooted
  under `target_info.repo_path` (`path.relative`-based, case-insensitive
  on Windows) while keeping `mcp__*`, `Write`, and everything else.
- **Windows test de-flake.** The `speca ask` streaming-render test no
  longer flakes on Windows runners.

## Tests

- 354 vitest cases (was 290 in v0.9.1) — +64 cases covering the corpus
  surfaces: export, gc, manifest, redact, runs, paths, and duration
  suites. Green on the matrix (ubuntu-22.04 / macOS 14 / windows-2022 ×
  Node 20 / 22).

## Issues closed

- [#32](https://github.com/NyxFoundation/speca/issues/32) — `speca
  corpus` subcommands (list / show / export / gc) on top of the per-run
  archive substrate.

## Install / upgrade

```bash
# Always-fresh
npx speca-cli@latest <command>

# Pin to this release
npx speca-cli@0.9.2 <command>

# Global install
npm install -g speca-cli
```

Requires **Node 20+**. For the audit pipeline you also need `uv`, `git`,
and `claude` (`speca doctor` checks all of them).

## Documentation

- [`cli/README.md`](https://github.com/NyxFoundation/speca/blob/main/cli/README.md) — usage guide
- [`cli/CHANGELOG.md`](https://github.com/NyxFoundation/speca/blob/main/cli/CHANGELOG.md) — full v0.9.2 entry
- [`cli/TESTING.md`](https://github.com/NyxFoundation/speca/blob/main/cli/TESTING.md) — manual test recipe
- [`docs/SPECA_CLI_SPEC.md`](https://github.com/NyxFoundation/speca/blob/main/docs/SPECA_CLI_SPEC.md) — design spec

---

**Full changelog:** https://github.com/NyxFoundation/speca/blob/main/cli/CHANGELOG.md
