import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULT_KEYBINDS,
  keysForAction,
  matchAny,
  matchKey,
  resetKeybindCache,
  resolveKeybinds,
} from "../src/lib/keybinds/index.js";
import { configFilePath } from "../src/lib/config/index.js";

let workDir: string;
let originalXdg: string | undefined;
let originalAppData: string | undefined;

beforeEach(async () => {
  workDir = await fs.mkdtemp(join(tmpdir(), "speca-keybinds-test-"));
  originalXdg = process.env.XDG_CONFIG_HOME;
  originalAppData = process.env.APPDATA;
  process.env.XDG_CONFIG_HOME = workDir;
  process.env.APPDATA = workDir;
  resetKeybindCache();
});

afterEach(async () => {
  if (originalXdg === undefined) delete process.env.XDG_CONFIG_HOME;
  else process.env.XDG_CONFIG_HOME = originalXdg;
  if (originalAppData === undefined) delete process.env.APPDATA;
  else process.env.APPDATA = originalAppData;
  resetKeybindCache();
  await fs.rm(workDir, { recursive: true, force: true });
});

async function writeConfig(body: string): Promise<void> {
  const target = configFilePath();
  await fs.mkdir(join(target, ".."), { recursive: true });
  await fs.writeFile(target, body, "utf8");
}

describe("matchKey", () => {
  it("matches single character descriptors against input", () => {
    expect(matchKey("q", "q", {})).toBe(true);
    expect(matchKey("q", "r", {})).toBe(false);
  });

  it("does not fire single-character bindings when ctrl is held", () => {
    expect(matchKey("q", "q", { ctrl: true })).toBe(false);
  });

  it("matches named modifier flags", () => {
    expect(matchKey("escape", "", { escape: true })).toBe(true);
    expect(matchKey("escape", "", {})).toBe(false);
    expect(matchKey("return", "", { return: true })).toBe(true);
    expect(matchKey("upArrow", "", { upArrow: true })).toBe(true);
  });

  it("matches ctrl+<letter> chords case-insensitively", () => {
    expect(matchKey("ctrl+c", "c", { ctrl: true })).toBe(true);
    expect(matchKey("ctrl+C", "c", { ctrl: true })).toBe(true);
    expect(matchKey("ctrl+c", "c", {})).toBe(false);
    expect(matchKey("ctrl+c", "v", { ctrl: true })).toBe(false);
  });

  it("returns false on unknown / empty descriptors", () => {
    expect(matchKey("", "q", {})).toBe(false);
    expect(matchKey("ctrl+", "c", { ctrl: true })).toBe(false);
    expect(matchKey("super+x", "x", {})).toBe(false);
  });

  it("matchAny iterates descriptors and short-circuits", () => {
    expect(matchAny(["q", "ctrl+c"], "q", {})).toBe(true);
    expect(matchAny(["q", "ctrl+c"], "c", { ctrl: true })).toBe(true);
    expect(matchAny(["q", "ctrl+c"], "v", {})).toBe(false);
  });
});

describe("resolveKeybinds", () => {
  it("returns the defaults when no overrides supplied", () => {
    const m = resolveKeybinds();
    expect(m.exit).toEqual(DEFAULT_KEYBINDS.exit);
    expect(m["toggle-log"]).toEqual(DEFAULT_KEYBINDS["toggle-log"]);
  });

  it("user overrides win on a per-action basis", () => {
    const m = resolveKeybinds({ exit: ["x"], "filter-mode": ["/"] });
    expect(m.exit).toEqual(["x"]);
    expect(m["filter-mode"]).toEqual(["/"]);
    // Untouched action keeps its default.
    expect(m["toggle-log"]).toEqual(DEFAULT_KEYBINDS["toggle-log"]);
  });

  it("ignores empty-array overrides (treated as 'keep default')", () => {
    const m = resolveKeybinds({ exit: [] });
    expect(m.exit).toEqual(DEFAULT_KEYBINDS.exit);
  });
});

describe("keysForAction (with on-disk config)", () => {
  it("returns the default when no config is present", () => {
    expect(keysForAction("exit")).toEqual(DEFAULT_KEYBINDS.exit);
  });

  it("returns the user's override when config.toml binds the action", async () => {
    await writeConfig(`[keybinds]
exit = ["x", "ctrl+d"]
`);
    expect(keysForAction("exit")).toEqual(["x", "ctrl+d"]);
  });

  it("returns [] for a totally unknown action", () => {
    expect(keysForAction("does-not-exist")).toEqual([]);
  });
});
