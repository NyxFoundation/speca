#!/usr/bin/env node
/**
 * vendor-core.mjs
 *
 * Copies the SPECA Python core from the repository root into
 * `cli/vendor/speca-core/` so it ships inside the speca-cli npm tarball
 * (issue #95: `speca run` must work from any directory, without a speca
 * checkout). At runtime the CLI resolves this directory via
 * `src/lib/core-root.ts` and spawns
 * `uv run --project <coreRoot> python <coreRoot>/scripts/run_phase.py`
 * with `SPECA_ROOT=<coreRoot>` in the child env.
 *
 * AUTO-GENERATED OUTPUT — DO NOT EDIT THE FILES IN vendor/.
 * The directory is gitignored; run `npm run vendor-core` to (re)build it.
 * The repository root remains the single source of truth.
 *
 * Like sync-schemas.mjs, the output is deliberately timestamp-free and
 * ordered deterministically so re-running on an unchanged source tree yields
 * byte-identical output.
 */
import { spawnSync } from "node:child_process";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
// smol-toml is a runtime dependency of the CLI (see package.json), so it is
// always present when this build script runs.
import { parse as parseToml } from "smol-toml";

const __dirname = dirname(fileURLToPath(import.meta.url));
const cliRoot = resolve(__dirname, "..");
const repoRoot = resolve(cliRoot, "..");
const targetRoot = join(cliRoot, "vendor", "speca-core");

function fail(message) {
  console.error(`[vendor-core] ${message}`);
  process.exit(1);
}

// Runtime cruft that must never leak into the tarball.
const EXCLUDED_DIR_NAMES = new Set(["__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"]);
const EXCLUDED_FILE_SUFFIXES = [".pyc", ".pyo"];
const EXCLUDED_FILE_NAMES = new Set([".DS_Store"]);

function isExcludedFile(name) {
  if (EXCLUDED_FILE_NAMES.has(name)) return true;
  return EXCLUDED_FILE_SUFFIXES.some((suffix) => name.endsWith(suffix));
}

/** Recursively copy `srcDir` into `dstDir`, sorted, minus excluded cruft. */
function copyTree(srcDir, dstDir, copied) {
  mkdirSync(dstDir, { recursive: true });
  // Sorted traversal keeps the manifest (and any downstream archiving)
  // byte-stable across filesystems that return entries in arbitrary order.
  const entries = readdirSync(srcDir, { withFileTypes: true }).sort((a, b) =>
    a.name < b.name ? -1 : a.name > b.name ? 1 : 0,
  );
  for (const entry of entries) {
    const src = join(srcDir, entry.name);
    const dst = join(dstDir, entry.name);
    if (entry.isDirectory()) {
      if (EXCLUDED_DIR_NAMES.has(entry.name)) continue;
      copyTree(src, dst, copied);
    } else if (entry.isFile()) {
      if (isExcludedFile(entry.name)) continue;
      copyFileSync(src, dst);
      copied.push(relative(targetRoot, dst).split(sep).join("/"));
    }
    // Symlinks/sockets are skipped: the core contains none, and copying
    // symlinks into an npm tarball is a portability trap.
  }
}

function copyFile(srcRel, copied) {
  const src = join(repoRoot, srcRel);
  if (!existsSync(src)) {
    fail(`expected core file not found: ${src}`);
  }
  const dst = join(targetRoot, srcRel);
  mkdirSync(dirname(dst), { recursive: true });
  copyFileSync(src, dst);
  copied.push(srcRel.split(sep).join("/"));
}

// ---------------------------------------------------------------------------
// Build the vendor tree from scratch (idempotent: stale files never survive).
// ---------------------------------------------------------------------------
rmSync(targetRoot, { recursive: true, force: true });
mkdirSync(targetRoot, { recursive: true });

const copied = [];

// `scripts/` is mostly dev tooling (scrapers, dataset builders); only the
// orchestrator runtime is whitelisted. Adding a file is cheap (append here),
// but we avoid shipping ad-hoc research scripts to every npm user.
const SCRIPT_FILES = ["scripts/__init__.py", "scripts/run_phase.py"];
for (const rel of SCRIPT_FILES) {
  copyFile(rel, copied);
}

// Whole-directory copies: everything under these is runtime surface.
const TREES = [
  "scripts/orchestrator",
  "prompts",
  "schemas",
  join(".claude", "skills"),
];
for (const rel of TREES) {
  const src = join(repoRoot, rel);
  if (!existsSync(src)) {
    fail(`expected core directory not found: ${src}`);
  }
  copyTree(src, join(targetRoot, rel), copied);
}

// ---------------------------------------------------------------------------
// Default MCP config (issue #98): npm installs have no scripts/setup_mcp.sh,
// so without this file the MCP-declaring phases (01a: fetch, 01b:
// fetch+filesystem, 02c: tree_sitter+filesystem) would start with ZERO
// servers. The orchestrator resolves .mcp.json in this order (see
// scripts/orchestrator/runner.py, _load_base_mcp_config):
//   $SPECA_MCP_CONFIG  ->  ./.mcp.json (user's workspace)  ->  THIS file.
// Only the servers a phase declares are actually started
// (--strict-mcp-config + per-phase filtering), so listing a server here does
// not launch it for phases that never asked for it. The `filesystem` entry
// uses "." — the server resolves it against its own cwd, which is the user's
// workspace when Claude spawns it there.
// ---------------------------------------------------------------------------
const defaultMcpConfig = {
  mcpServers: {
    fetch: {
      type: "stdio",
      command: "uvx",
      args: ["mcp-server-fetch"],
    },
    filesystem: {
      type: "stdio",
      command: "npx",
      args: ["-y", "@modelcontextprotocol/server-filesystem", "."],
    },
    tree_sitter: {
      type: "stdio",
      command: "uvx",
      args: ["mcp-server-tree-sitter"],
    },
  },
};
writeFileSync(
  join(targetRoot, ".mcp.json"),
  `${JSON.stringify(defaultMcpConfig, null, 2)}\n`,
  "utf8",
);
copied.push(".mcp.json");

// ---------------------------------------------------------------------------
// Project metadata so `uv run --project <coreRoot>` can resolve the core's
// Python dependencies without a speca checkout.
//
// The root pyproject.toml must NOT be copied verbatim: it declares a
// hatchling build backend that packages `web/` (which the vendored tree
// deliberately omits — uv would try to build it and hatchling would fail),
// plus web-only deps, entry points and dev dependency groups the core
// never needs. Instead we GENERATE a core-only pyproject.toml:
//   - `dependencies` comes from the root `[tool.speca].core-dependencies`
//     table, the declared dependency list of the Python core alone (the
//     root `[project].dependencies` also carries web/CI-only packages like
//     fastapi and sweagent that must not ship to npm users);
//   - `requires-python` and `version` come from the root `[project]` table.
// Both are read at build time so the vendored copy cannot silently drift
// from the root file.
// ---------------------------------------------------------------------------
const rootPyprojectPath = join(repoRoot, "pyproject.toml");
if (!existsSync(rootPyprojectPath)) {
  fail(`expected core file not found: ${rootPyprojectPath}`);
}
let rootPyproject;
try {
  rootPyproject = parseToml(readFileSync(rootPyprojectPath, "utf8"));
} catch (err) {
  fail(`failed to parse ${rootPyprojectPath}: ${err.message}`);
}

// Hard-fail on unexpected shape: shipping an empty dependency list would
// "work" at build time and break every npm user at runtime.
const rootProject = rootPyproject.project;
if (typeof rootProject !== "object" || rootProject === null || Array.isArray(rootProject)) {
  fail(`root pyproject.toml has no [project] table: ${rootPyprojectPath}`);
}
const { "requires-python": requiresPython, version: rootVersion } = rootProject;
if (typeof requiresPython !== "string" || requiresPython.length === 0) {
  fail("root pyproject.toml [project].requires-python is missing or not a string");
}
if (typeof rootVersion !== "string" || rootVersion.length === 0) {
  fail("root pyproject.toml [project].version is missing or not a string");
}
const toolSpeca = rootPyproject.tool?.speca;
if (typeof toolSpeca !== "object" || toolSpeca === null || Array.isArray(toolSpeca)) {
  fail(`root pyproject.toml has no [tool.speca] table: ${rootPyprojectPath}`);
}
const dependencies = toolSpeca["core-dependencies"];
if (
  !Array.isArray(dependencies) ||
  dependencies.length === 0 ||
  dependencies.some((d) => typeof d !== "string")
) {
  fail(
    "root pyproject.toml [tool.speca].core-dependencies is missing, empty, or not a string array",
  );
}

// JSON string escaping is a valid subset of TOML basic-string escaping for
// the requirement specifiers we emit.
const tomlString = (s) => JSON.stringify(s);

const generatedPyproject = [
  "# AUTO-GENERATED — DO NOT EDIT.",
  "# Generated by cli/scripts/vendor-core.mjs (run via `npm run vendor-core`).",
  "#",
  "# `dependencies` is derived at build time from the repository root",
  "# pyproject.toml `[tool.speca].core-dependencies` table (the declared",
  "# dependency list of the Python core); `requires-python` and `version`",
  "# come from its `[project]` table. Everything web/CI-only — the hatchling",
  "# build backend, web deps, `[project.scripts]` and the dev dependency",
  "# groups — is intentionally dropped: the vendored core is loose scripts",
  "# run by path, not an installable package.",
  "",
  "[project]",
  'name = "speca-core"',
  `version = ${tomlString(rootVersion)}`,
  `requires-python = ${tomlString(requiresPython)}`,
  "dependencies = [",
  ...dependencies.map((d) => `  ${tomlString(d)},`),
  "]",
  "",
  "# Tell uv this project is NOT an installable package: install only the",
  "# dependencies into the venv and never invoke a build backend (there is no",
  "# web/ tree here for hatchling to build).",
  "[tool.uv]",
  "package = false",
  "",
].join("\n");
writeFileSync(join(targetRoot, "pyproject.toml"), generatedPyproject, "utf8");
copied.push("pyproject.toml");

// uv.lock: the root lock is keyed to the root pyproject (full dependency set
// plus dev/benchmark/datasets groups) and would be rejected — and silently
// re-locked — by uv against the generated core-only pyproject, so copying it
// is worse than shipping none. Instead, generate a matching lock here when
// `uv` is available (it is on the publishing machine/CI). When it is not,
// skip WITHOUT failing the build: the published package then resolves its
// dependencies on first run.
const uvProbe = spawnSync("uv", ["--version"], { stdio: "ignore" });
if (uvProbe.error || uvProbe.status !== 0) {
  console.warn(
    "[vendor-core] WARNING: `uv` not found on PATH — skipping uv.lock generation.\n" +
      "[vendor-core] The published package will resolve Python dependencies on first run.\n" +
      "[vendor-core] Publish from a machine with uv installed to ship a lock file.",
  );
} else {
  const lock = spawnSync("uv", ["lock", "--directory", targetRoot], { stdio: "inherit" });
  if (lock.error || lock.status !== 0) {
    fail("`uv lock` failed for the generated vendor pyproject.toml (see output above)");
  }
  if (!existsSync(join(targetRoot, "uv.lock"))) {
    fail("`uv lock` reported success but produced no uv.lock");
  }
  copied.push("uv.lock");
}

// Self-documenting marker for anyone browsing an installed package.
// Timestamp-free on purpose (see sync-schemas.mjs) so rebuilds on an
// unchanged tree are byte-identical.
const readme = [
  "# speca-core (vendored)",
  "",
  "AUTO-GENERATED — DO NOT EDIT.",
  "",
  "This directory is a build-time copy of the SPECA Python core (the",
  "orchestrator in `scripts/`, plus `prompts/`, `schemas/` and",
  "`.claude/skills/`) produced by `cli/scripts/vendor-core.mjs`",
  "(run via `npm run vendor-core`). It is bundled into the npm tarball so",
  "`speca run` works from any directory without a speca checkout.",
  "",
  "The originals at the repository root are the single source of truth.",
  "",
  "`pyproject.toml` here is NOT a copy of the root file: it is generated",
  "core-only metadata (dependencies derived from the root",
  "`[tool.speca].core-dependencies` table, plus `[tool.uv] package = false`",
  "so uv never invokes a build backend).",
  "`uv.lock` is generated against it at build time when uv is available.",
  "",
  "`.mcp.json` here is a generated default MCP server config, used by the",
  "orchestrator only when neither `SPECA_MCP_CONFIG` nor a workspace",
  "`.mcp.json` provides one (see scripts/orchestrator/runner.py).",
  "",
].join("\n");
writeFileSync(join(targetRoot, "README.md"), readme, "utf8");

const manifest = {
  generator: "cli/scripts/vendor-core.mjs",
  source: "repository root (scripts/, prompts/, schemas/, .claude/skills/)",
  note: "AUTO-GENERATED — DO NOT EDIT. Run `npm run vendor-core` to refresh.",
  files: copied,
};
writeFileSync(
  join(targetRoot, "manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8",
);

// Guard: the runtime marker core-root.ts looks for must exist, and no
// bytecode cache may have slipped through.
if (!existsSync(join(targetRoot, "scripts", "run_phase.py"))) {
  fail("post-condition failed: vendor/speca-core/scripts/run_phase.py missing");
}
if (copied.some((f) => f.includes("__pycache__") || f.endsWith(".pyc"))) {
  fail("post-condition failed: bytecode cache leaked into vendor output");
}

console.log(`[vendor-core] copied ${copied.length} file(s) to ${targetRoot}`);
