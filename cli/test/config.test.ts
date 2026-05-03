import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { configFilePath, loadUserConfig } from "../src/lib/config/index.js";

let workDir: string;
let originalXdg: string | undefined;
let originalAppData: string | undefined;

beforeEach(async () => {
  workDir = await fs.mkdtemp(join(tmpdir(), "speca-config-test-"));
  originalXdg = process.env.XDG_CONFIG_HOME;
  originalAppData = process.env.APPDATA;
  process.env.XDG_CONFIG_HOME = workDir;
  process.env.APPDATA = workDir;
});

afterEach(async () => {
  if (originalXdg === undefined) delete process.env.XDG_CONFIG_HOME;
  else process.env.XDG_CONFIG_HOME = originalXdg;
  if (originalAppData === undefined) delete process.env.APPDATA;
  else process.env.APPDATA = originalAppData;
  await fs.rm(workDir, { recursive: true, force: true });
});

async function writeConfig(body: string): Promise<string> {
  const target = configFilePath();
  await fs.mkdir(join(target, ".."), { recursive: true });
  await fs.writeFile(target, body, "utf8");
  return target;
}

describe("configFilePath", () => {
  it("returns a path ending in speca/config.toml", () => {
    const p = configFilePath();
    expect(p.endsWith(join("speca", "config.toml"))).toBe(true);
  });
});

describe("loadUserConfig", () => {
  it("returns defaults when no file exists", () => {
    const cfg = loadUserConfig();
    expect(cfg.theme).toBe("dark");
    expect(cfg.keybinds).toEqual({});
  });

  it("parses theme + keybinds from a valid TOML file", async () => {
    await writeConfig(`theme = "light"

[keybinds]
exit = ["q", "ctrl+c"]
toggle-log = ["l"]
`);
    const cfg = loadUserConfig();
    expect(cfg.theme).toBe("light");
    expect(cfg.keybinds.exit).toEqual(["q", "ctrl+c"]);
    expect(cfg.keybinds["toggle-log"]).toEqual(["l"]);
  });

  it("falls back to defaults on malformed TOML", async () => {
    await writeConfig("this is not valid toml = = = = =\n[keybinds\n");
    const cfg = loadUserConfig();
    expect(cfg.theme).toBe("dark");
    expect(cfg.keybinds).toEqual({});
  });

  it("ignores keybind entries that are not string arrays", async () => {
    await writeConfig(`theme = "dark"

[keybinds]
exit = ["q"]
toggle-log = "l"
weird = [1, 2, 3]
`);
    const cfg = loadUserConfig();
    expect(cfg.keybinds.exit).toEqual(["q"]);
    expect(cfg.keybinds["toggle-log"]).toBeUndefined();
    expect(cfg.keybinds.weird).toBeUndefined();
  });

  it("falls back to default theme when the value is not a string", async () => {
    await writeConfig(`theme = 42\n`);
    const cfg = loadUserConfig();
    expect(cfg.theme).toBe("dark");
  });
});
