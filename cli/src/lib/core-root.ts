/**
 * Resolve the SPECA core root — the directory containing the Python
 * orchestrator assets (`scripts/`, `prompts/`, `schemas/`, `.claude/skills/`).
 *
 * The npm package bundles a copy of the core under `vendor/speca-core/`
 * (produced at build time by `cli/scripts/vendor-core.mjs`), so `speca run`
 * works from ANY directory without a speca checkout (issue #95). Resolution
 * precedence:
 *
 *   1. `SPECA_ROOT` env var — explicit escape hatch (also how tests inject).
 *   2. Layout-dependent, located relative to this module
 *      (`import.meta.url`), NEVER relative to the user's cwd:
 *      - Running from `dist/` (the published-package layout): the vendored
 *        core shipped inside the npm package, falling back to a checkout
 *        repo root.
 *      - Running from `src/` (dev: `npm run dev` / tsx / vitest): the
 *        checkout repo root FIRST — `cli/vendor/` is a build artifact that
 *        merely running the test suite creates, and a stale vendored copy
 *        must never shadow the live sources a dev is editing — falling back
 *        to the vendored core.
 *
 * The resolved path is handed to the orchestrator both as
 * `uv run --project <coreRoot>` and as the `SPECA_ROOT` env var; the Python
 * side (`scripts/orchestrator/paths.py`) reads `SPECA_ROOT` to locate its
 * prompts/schemas/skills while cwd stays in the user's workspace.
 */
import { existsSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** Marker file that must exist for a directory to count as a core root. */
const CORE_MARKER = join("scripts", "run_phase.py");

export interface ResolveCoreRootOptions {
  /** Environment to consult (defaults to `process.env`). Injection seam for tests. */
  env?: Record<string, string | undefined>;
  /**
   * Module URL to resolve the vendored core against (defaults to this
   * module's `import.meta.url`). Injection seam for tests.
   */
  moduleUrl?: string;
  /** Existence probe (defaults to `fs.existsSync`). Injection seam for tests. */
  exists?: (path: string) => boolean;
}

/** True when `dir` looks like a SPECA core root (contains run_phase.py). */
export function isCoreRoot(
  dir: string,
  exists: (path: string) => boolean = existsSync,
): boolean {
  return exists(join(dir, CORE_MARKER));
}

/**
 * Resolve the core root, or throw an Error with an actionable message when
 * no core can be located.
 */
export function resolveCoreRoot(opts: ResolveCoreRootOptions = {}): string {
  const env = opts.env ?? process.env;
  const exists = opts.exists ?? existsSync;
  const moduleUrl = opts.moduleUrl ?? import.meta.url;

  // 1. Explicit override. Trusted as-is (escape hatch) — `speca doctor`
  //    reports when it points somewhere without a core.
  const envRoot = env["SPECA_ROOT"];
  if (envRoot && envRoot.trim() !== "") {
    return resolve(envRoot);
  }

  // This module lives two levels below the package root in both the compiled
  // layout (dist/lib/core-root.js) and the source layout (src/lib/core-root.ts),
  // so `../..` of the module directory is the cli package root either way.
  const moduleDir = dirname(fileURLToPath(moduleUrl));
  const packageRoot = resolve(moduleDir, "..", "..");

  // Vendored core bundled with the npm package (a build artifact in a dev
  // checkout), and the repo root of a speca checkout (where the package root
  // is `cli/` and scripts/prompts/schemas live one level up).
  const vendored = join(packageRoot, "vendor", "speca-core");
  const repoRoot = resolve(packageRoot, "..");

  // 2./3. Layout-dependent order. Running from `src/` means dev (tsx,
  // vitest): the live checkout must win, because `cli/vendor/` gets created
  // as a side effect of running the test suite and a stale vendored copy
  // would silently shadow the sources the dev is editing. Running from
  // `dist/` means the compiled/published layout, where the vendored core is
  // the intended runtime payload.
  const isDevLayout = basename(resolve(moduleDir, "..")) === "src";
  const candidates = isDevLayout ? [repoRoot, vendored] : [vendored, repoRoot];
  for (const candidate of candidates) {
    if (isCoreRoot(candidate, exists)) {
      return candidate;
    }
  }

  throw new Error(
    "speca: cannot locate the bundled Python core (scripts/run_phase.py).\n" +
      `  Looked for: ${vendored} and ${repoRoot}\n` +
      "  Reinstall the package (npm install -g speca-cli) or set SPECA_ROOT to a\n" +
      "  speca checkout. Run `speca doctor` for a full environment diagnosis.",
  );
}
