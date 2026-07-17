import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { isCoreRoot, resolveCoreRoot } from "../src/lib/core-root.js";

/**
 * resolveCoreRoot() precedence (issue #95):
 *   1. SPECA_ROOT env var,
 *   2. layout-dependent (resolved via import.meta.url, never cwd):
 *      running from dist/ prefers the vendored core, then the checkout repo
 *      root; running from src/ (dev) prefers the checkout repo root, then
 *      the vendored core — so a stale cli/vendor/ tree (a mere build
 *      artifact of the test suite) never shadows live sources in dev,
 * and an actionable error when nothing is found.
 *
 * The fake package layouts are materialised on disk; `moduleUrl` and `env`
 * are injected through the options seam so the test never mutates
 * process.env or depends on where vitest itself runs.
 */

let tmp: string;
beforeEach(() => {
  // realpathSync: macOS tmpdir is a /var -> /private/var symlink; resolve it
  // so path equality assertions compare like with like.
  tmp = realpathSync(mkdtempSync(join(tmpdir(), "speca-core-root-")));
});
afterEach(() => {
  rmSync(tmp, { recursive: true, force: true });
});

/** Create `<dir>/scripts/run_phase.py` so `dir` qualifies as a core root. */
function makeCoreRoot(dir: string): string {
  mkdirSync(join(dir, "scripts"), { recursive: true });
  writeFileSync(join(dir, "scripts", "run_phase.py"), "# fake core\n", "utf8");
  return dir;
}

/** file:// URL of a fake compiled module at `<packageRoot>/dist/lib/core-root.js`. */
function moduleUrlAt(packageRoot: string): string {
  return pathToFileURL(join(packageRoot, "dist", "lib", "core-root.js")).href;
}

describe("resolveCoreRoot — precedence", () => {
  it("1. SPECA_ROOT wins over an existing vendored core", () => {
    const packageRoot = join(tmp, "node_modules", "speca-cli");
    makeCoreRoot(join(packageRoot, "vendor", "speca-core"));
    const override = makeCoreRoot(join(tmp, "my-speca-checkout"));

    const root = resolveCoreRoot({
      env: { SPECA_ROOT: override },
      moduleUrl: moduleUrlAt(packageRoot),
    });
    expect(root).toBe(resolve(override));
  });

  it("2. falls back to the vendored core relative to the module, not the cwd", () => {
    const packageRoot = join(tmp, "node_modules", "speca-cli");
    const vendored = makeCoreRoot(join(packageRoot, "vendor", "speca-core"));

    const root = resolveCoreRoot({
      env: {}, // no SPECA_ROOT
      moduleUrl: moduleUrlAt(packageRoot),
    });
    expect(root).toBe(vendored);
  });

  it("3. dev fallback: uses the checkout repo root when vendor/ is not built", () => {
    const repoRoot = makeCoreRoot(join(tmp, "speca"));
    // Module runs from cli/src/lib (tsx dev) — same depth as dist/lib.
    const moduleUrl = pathToFileURL(
      join(repoRoot, "cli", "src", "lib", "core-root.ts"),
    ).href;

    const root = resolveCoreRoot({ env: {}, moduleUrl });
    expect(root).toBe(repoRoot);
  });

  it("dev layout (src/): the checkout repo root wins over a stale vendor tree", () => {
    // Running the test suite builds cli/vendor/speca-core as a side effect;
    // it must never shadow the live sources a dev is editing.
    const repoRoot = makeCoreRoot(join(tmp, "speca"));
    makeCoreRoot(join(repoRoot, "cli", "vendor", "speca-core"));
    const moduleUrl = pathToFileURL(
      join(repoRoot, "cli", "src", "lib", "core-root.ts"),
    ).href;

    const root = resolveCoreRoot({ env: {}, moduleUrl });
    expect(root).toBe(repoRoot);
  });

  it("dist layout: the vendored core wins over a sibling checkout root", () => {
    const repoRoot = makeCoreRoot(join(tmp, "speca"));
    const vendored = makeCoreRoot(join(repoRoot, "cli", "vendor", "speca-core"));
    const moduleUrl = moduleUrlAt(join(repoRoot, "cli"));

    const root = resolveCoreRoot({ env: {}, moduleUrl });
    expect(root).toBe(vendored);
  });

  it("dev layout (src/): falls back to the vendored core when the repo root has no core", () => {
    const packageRoot = join(tmp, "not-a-checkout", "cli");
    const vendored = makeCoreRoot(join(packageRoot, "vendor", "speca-core"));
    const moduleUrl = pathToFileURL(
      join(packageRoot, "src", "lib", "core-root.ts"),
    ).href;

    const root = resolveCoreRoot({ env: {}, moduleUrl });
    expect(root).toBe(vendored);
  });

  it("ignores an empty/whitespace SPECA_ROOT and continues down the chain", () => {
    const packageRoot = join(tmp, "node_modules", "speca-cli");
    const vendored = makeCoreRoot(join(packageRoot, "vendor", "speca-core"));

    const root = resolveCoreRoot({
      env: { SPECA_ROOT: "  " },
      moduleUrl: moduleUrlAt(packageRoot),
    });
    expect(root).toBe(vendored);
  });

  it("throws an actionable error mentioning `speca doctor` when nothing is found", () => {
    const packageRoot = join(tmp, "empty-pkg");
    mkdirSync(join(packageRoot, "dist", "lib"), { recursive: true });

    expect(() =>
      resolveCoreRoot({ env: {}, moduleUrl: moduleUrlAt(packageRoot) }),
    ).toThrowError(/speca doctor/);
    expect(() =>
      resolveCoreRoot({ env: {}, moduleUrl: moduleUrlAt(packageRoot) }),
    ).toThrowError(/SPECA_ROOT/);
  });
});

describe("isCoreRoot", () => {
  it("requires scripts/run_phase.py", () => {
    expect(isCoreRoot(tmp)).toBe(false);
    makeCoreRoot(tmp);
    expect(isCoreRoot(tmp)).toBe(true);
  });
});
