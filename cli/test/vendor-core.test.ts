import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parse as parseToml } from "smol-toml";
import { beforeAll, describe, expect, it } from "vitest";

const __dirname = dirname(fileURLToPath(import.meta.url));
const cliRoot = resolve(__dirname, "..");
const repoRoot = resolve(cliRoot, "..");
const scriptPath = resolve(cliRoot, "scripts", "vendor-core.mjs");
const vendorDir = resolve(cliRoot, "vendor", "speca-core");

function runScript(): void {
  execFileSync(process.execPath, [scriptPath], { cwd: cliRoot, stdio: "pipe" });
}

/**
 * Aggregate sha256 over the vendor tree (sorted relative path + content per
 * file) so byte-stability across reruns is a single string comparison.
 */
function hashTree(dir: string, prefix = ""): string {
  const hash = createHash("sha256");
  const walk = (d: string, rel: string): void => {
    const entries = readdirSync(d, { withFileTypes: true }).sort((a, b) =>
      a.name < b.name ? -1 : a.name > b.name ? 1 : 0,
    );
    for (const entry of entries) {
      const abs = join(d, entry.name);
      const entryRel = rel ? `${rel}/${entry.name}` : entry.name;
      if (entry.isDirectory()) {
        walk(abs, entryRel);
      } else if (entry.isFile()) {
        hash.update(entryRel);
        hash.update("\0");
        hash.update(readFileSync(abs));
        hash.update("\0");
      }
    }
  };
  walk(dir, prefix);
  return hash.digest("hex");
}

describe("vendor-core.mjs", () => {
  beforeAll(() => {
    runScript();
  });

  it("writes the vendored core tree, manifest and README", () => {
    expect(existsSync(resolve(vendorDir, "scripts", "run_phase.py"))).toBe(true);
    expect(existsSync(resolve(vendorDir, "scripts", "orchestrator"))).toBe(true);
    expect(existsSync(resolve(vendorDir, "prompts"))).toBe(true);
    expect(existsSync(resolve(vendorDir, "schemas"))).toBe(true);
    expect(existsSync(resolve(vendorDir, ".claude", "skills"))).toBe(true);
    expect(existsSync(resolve(vendorDir, "manifest.json"))).toBe(true);
    expect(existsSync(resolve(vendorDir, "README.md"))).toBe(true);
    expect(existsSync(resolve(vendorDir, "pyproject.toml"))).toBe(true);
  });

  it("generates a core-only pyproject.toml (not a verbatim copy of the root)", () => {
    const raw = readFileSync(resolve(vendorDir, "pyproject.toml"), "utf8");
    const rootRaw = readFileSync(resolve(repoRoot, "pyproject.toml"), "utf8");
    expect(raw).not.toBe(rootRaw);

    // Generated-file header, naming the generator.
    expect(raw).toMatch(/AUTO-GENERATED/);
    expect(raw).toMatch(/vendor-core\.mjs/);

    const parsed = parseToml(raw) as Record<string, any>;
    expect(parsed.project.name).toBe("speca-core");

    // The key line: uv must treat the vendored core as a non-package so it
    // never invokes a build backend (there is no web/ tree to build here).
    expect(parsed.tool.uv.package).toBe(false);

    // Web-only / dev-only tables must not be carried over.
    expect(parsed["build-system"]).toBeUndefined();
    expect(parsed.project.scripts).toBeUndefined();
    expect(parsed.project["optional-dependencies"]).toBeUndefined();
    expect(parsed["dependency-groups"]).toBeUndefined();
    expect(parsed.tool.hatch).toBeUndefined();
    expect(parsed.tool.pytest).toBeUndefined();
  });

  it("derives dependencies and requires-python from the root pyproject (drift-safety)", () => {
    const generated = parseToml(
      readFileSync(resolve(vendorDir, "pyproject.toml"), "utf8"),
    ) as Record<string, any>;
    const root = parseToml(
      readFileSync(resolve(repoRoot, "pyproject.toml"), "utf8"),
    ) as Record<string, any>;

    // Independent parse of the root file: if the script hardcoded the list,
    // any edit to the root [tool.speca].core-dependencies table would fail
    // this assertion. That table — NOT [project].dependencies, which also
    // carries web/CI-only packages — declares what the vendored core needs.
    expect(generated.project.dependencies).toEqual(root.tool.speca["core-dependencies"]);
    expect(generated.project["requires-python"]).toBe(root.project["requires-python"]);
    expect(generated.project.version).toBe(root.project.version);
    expect(generated.project.dependencies.length).toBeGreaterThan(0);
  });

  it("lists the generated pyproject.toml in the manifest", () => {
    const manifest = JSON.parse(
      readFileSync(resolve(vendorDir, "manifest.json"), "utf8"),
    );
    expect(manifest.generator).toBe("cli/scripts/vendor-core.mjs");
    expect(manifest.files).toContain("pyproject.toml");
    expect(manifest.files).toContain("scripts/run_phase.py");
  });

  it("does not ship the root uv.lock verbatim", () => {
    // Either no lock (uv unavailable at build time — deps resolve on first
    // run) or a lock generated against the core-only pyproject, which can
    // never be byte-identical to the root lock (different project name and
    // dependency graph).
    const vendorLock = resolve(vendorDir, "uv.lock");
    const rootLock = resolve(repoRoot, "uv.lock");
    if (existsSync(vendorLock) && existsSync(rootLock)) {
      expect(readFileSync(vendorLock, "utf8")).not.toBe(readFileSync(rootLock, "utf8"));
    }
  });

  it("leaks no bytecode cache into the vendor tree", () => {
    const manifest = JSON.parse(
      readFileSync(resolve(vendorDir, "manifest.json"), "utf8"),
    );
    for (const f of manifest.files as string[]) {
      expect(f).not.toMatch(/__pycache__/);
      expect(f).not.toMatch(/\.pyc$/);
    }
  });

  it("is byte-stable across reruns on an unchanged source tree", () => {
    const first = hashTree(vendorDir);
    runScript();
    const second = hashTree(vendorDir);
    expect(second).toBe(first);
  });
});
