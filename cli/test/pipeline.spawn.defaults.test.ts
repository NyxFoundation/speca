import { EventEmitter } from "node:events";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { isAbsolute, join, resolve } from "node:path";
import { PassThrough } from "node:stream";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Issue #95 regression coverage for the DEFAULT spawn shape (no
 * `command`/`baseArgs` test seams): the CLI must launch
 *
 *   uv run --project <coreRoot> python <coreRoot>/scripts/run_phase.py …
 *
 * with an ABSOLUTE script path, `SPECA_ROOT=<coreRoot>` in the child env and
 * cwd = the user's workspace. The old default (`uv run python3
 * scripts/run_phase.py`) resolved the script against the user's cwd and let
 * uv discover the wrong project, so runs outside the speca checkout sat at
 * "idle" forever.
 *
 * `node:child_process.spawn` is mocked so we can inspect the exact
 * argv/options without needing uv installed.
 */

const spawnMock = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:child_process")>();
  return { ...actual, spawn: spawnMock };
});

import { defaultVenvDir, spawnPipeline } from "../src/lib/pipeline/spawn.js";

interface FakeChild extends EventEmitter {
  stdout: PassThrough;
  stderr: PassThrough;
  exitCode: number | null;
  pid: number;
  kill: (signal?: string) => boolean;
}

function makeFakeChild(): FakeChild {
  const child = new EventEmitter() as FakeChild;
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  child.exitCode = null;
  child.pid = 4242;
  child.kill = () => true;
  return child;
}

let tmp: string;
let coreRoot: string;
let workspace: string;

beforeEach(() => {
  spawnMock.mockReset();
  tmp = mkdtempSync(join(tmpdir(), "speca-spawn-defaults-"));
  coreRoot = join(tmp, "core");
  mkdirSync(join(coreRoot, "scripts"), { recursive: true });
  writeFileSync(join(coreRoot, "scripts", "run_phase.py"), "# fake\n", "utf8");
  workspace = join(tmp, "user-repo");
  mkdirSync(workspace, { recursive: true });
});
afterEach(() => {
  rmSync(tmp, { recursive: true, force: true });
});

async function finish(child: FakeChild): Promise<void> {
  child.emit("close", 0, null);
}

describe("spawnPipeline — default command shape (issue #95)", () => {
  it("spawns `uv run --project <coreRoot> python <abs run_phase.py>` with SPECA_ROOT set and cwd = the user's workspace", async () => {
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);

    const handle = spawnPipeline({
      phases: ["01a"],
      cwd: workspace,
      env: { SPECA_ROOT: coreRoot },
    });
    await finish(child);
    await handle.done;

    expect(spawnMock).toHaveBeenCalledTimes(1);
    const [command, args, options] = spawnMock.mock.calls[0] as [
      string,
      string[],
      { cwd?: string; env?: NodeJS.ProcessEnv },
    ];

    expect(command).toBe("uv");
    const scriptPath = join(resolve(coreRoot), "scripts", "run_phase.py");
    expect(args.slice(0, 5)).toEqual([
      "run",
      "--project",
      resolve(coreRoot),
      "python",
      scriptPath,
    ]);
    // The regression that IS #95: the script path must be absolute, never
    // resolved against the user's cwd.
    expect(isAbsolute(args[4]!)).toBe(true);
    // `python`, not `python3` — python3 exits 9009 in the Windows uv venv.
    expect(args).toContain("python");
    expect(args).not.toContain("python3");
    expect(args).toContain("--json");
    expect(args).toContain("--phase");
    expect(args).toContain("01a");

    // The orchestrator observes the user's repo and writes outputs/ there.
    expect(options.cwd).toBe(workspace);
    // The Python side resolves prompts/schemas/skills via SPECA_ROOT.
    expect(options.env?.SPECA_ROOT).toBe(resolve(coreRoot));
  });

  it("defaults cwd to process.cwd() when no workspace is given", async () => {
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);

    const handle = spawnPipeline({
      target: "03",
      env: { SPECA_ROOT: coreRoot },
    });
    await finish(child);
    await handle.done;

    const [, args, options] = spawnMock.mock.calls[0] as [
      string,
      string[],
      { cwd?: string },
    ];
    expect(options.cwd).toBe(process.cwd());
    expect(args).toContain("--target");
    expect(args).toContain("03");
  });

  it("falls back to the dev checkout core when no SPECA_ROOT is set", async () => {
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);

    // Tests run from the speca checkout: with no override and no vendor/
    // requirement, resolveCoreRoot lands on a directory that really contains
    // scripts/run_phase.py (either cli/vendor/speca-core or the repo root).
    const handle = spawnPipeline({
      phases: ["01a"],
      cwd: workspace,
      env: { SPECA_ROOT: undefined },
    });
    await finish(child);
    await handle.done;

    const [command, args, options] = spawnMock.mock.calls[0] as [
      string,
      string[],
      { env?: NodeJS.ProcessEnv },
    ];
    expect(command).toBe("uv");
    expect(args[1]).toBe("--project");
    expect(isAbsolute(args[2]!)).toBe(true);
    expect(args[3]).toBe("python");
    expect(isAbsolute(args[4]!)).toBe(true);
    expect(args[4]!.endsWith(join("scripts", "run_phase.py"))).toBe(true);
    expect(options.env?.SPECA_ROOT).toBe(args[2]);
  });

  it("does NOT resolve a core root when the command/baseArgs test seams are used", async () => {
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);

    const handle = spawnPipeline({
      phases: ["01a"],
      command: process.execPath,
      baseArgs: ["/some/fake/script.mjs"],
      env: { SPECA_ROOT: undefined },
    });
    await finish(child);
    await handle.done;

    const [command, args, options] = spawnMock.mock.calls[0] as [
      string,
      string[],
      { env?: NodeJS.ProcessEnv },
    ];
    expect(command).toBe(process.execPath);
    expect(args[0]).toBe("/some/fake/script.mjs");
    // Injected argv means the resolver never ran; no SPECA_ROOT is forced in,
    // and no uv venv redirection is applied either.
    expect(options.env?.SPECA_ROOT).toBeUndefined();
    expect(options.env?.UV_PROJECT_ENVIRONMENT).toBeUndefined();
  });
});

describe("spawnPipeline — UV_PROJECT_ENVIRONMENT (venv outside node_modules)", () => {
  it("redirects uv's venv to a user-writable cache dir on the default path", async () => {
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);

    const cacheHome = join(tmp, "xdg-cache");
    const handle = spawnPipeline({
      phases: ["01a"],
      cwd: workspace,
      env: {
        SPECA_ROOT: coreRoot,
        XDG_CACHE_HOME: cacheHome,
        UV_PROJECT_ENVIRONMENT: undefined,
      },
    });
    await finish(child);
    await handle.done;

    const [, , options] = spawnMock.mock.calls[0] as [
      string,
      string[],
      { env?: NodeJS.ProcessEnv },
    ];
    const venv = options.env?.UV_PROJECT_ENVIRONMENT;
    // Without this, uv creates <coreRoot>/.venv — inside node_modules for an
    // installed package, EACCES after `sudo npm i -g` (issue #95 review).
    expect(venv).toBeDefined();
    expect(isAbsolute(venv!)).toBe(true);
    expect(venv!.startsWith(join(cacheHome, "speca"))).toBe(true);
    expect(venv!.startsWith(resolve(coreRoot))).toBe(false);
    expect(venv).toBe(defaultVenvDir(resolve(coreRoot), options.env!));
  });

  it("never overrides a UV_PROJECT_ENVIRONMENT the user already set", async () => {
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);

    const userVenv = join(tmp, "my-own-venv");
    const handle = spawnPipeline({
      phases: ["01a"],
      cwd: workspace,
      env: { SPECA_ROOT: coreRoot, UV_PROJECT_ENVIRONMENT: userVenv },
    });
    await finish(child);
    await handle.done;

    const [, , options] = spawnMock.mock.calls[0] as [
      string,
      string[],
      { env?: NodeJS.ProcessEnv },
    ];
    expect(options.env?.UV_PROJECT_ENVIRONMENT).toBe(userVenv);
  });

  it("defaultVenvDir keys the venv by core root and honors XDG_CACHE_HOME", () => {
    const cacheHome = join(tmp, "cache");
    const a = defaultVenvDir("/opt/core-a", { XDG_CACHE_HOME: cacheHome });
    const b = defaultVenvDir("/opt/core-b", { XDG_CACHE_HOME: cacheHome });
    expect(a).not.toBe(b);
    expect(a.startsWith(join(cacheHome, "speca", "venvs"))).toBe(true);
    // Stable for the same root.
    expect(defaultVenvDir("/opt/core-a", { XDG_CACHE_HOME: cacheHome })).toBe(a);
    // Falls back to ~/.cache when XDG_CACHE_HOME is unset or blank.
    const noXdg = defaultVenvDir("/opt/core-a", { XDG_CACHE_HOME: "  " });
    expect(noXdg.includes(join(".cache", "speca", "venvs"))).toBe(true);
  });
});
