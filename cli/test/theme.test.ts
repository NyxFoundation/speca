import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULT_THEME,
  getTheme,
  loadTheme,
  themes,
} from "../src/lib/theme/index.js";
import { configFilePath } from "../src/lib/config/index.js";

let workDir: string;
let originalXdg: string | undefined;
let originalAppData: string | undefined;

beforeEach(async () => {
  workDir = await fs.mkdtemp(join(tmpdir(), "speca-theme-test-"));
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

describe("themes registry", () => {
  it("ships dark, light, and solarized themes", () => {
    expect(Object.keys(themes).sort()).toEqual(["dark", "light", "solarized"]);
  });

  it("defines every required colour key on every theme", () => {
    const required = [
      "primary",
      "secondary",
      "success",
      "warn",
      "error",
      "info",
      "dim",
      "text",
      "muted",
      "border",
    ] as const;
    for (const theme of Object.values(themes)) {
      for (const key of required) {
        expect(typeof theme.colors[key]).toBe("string");
        expect(theme.colors[key].length).toBeGreaterThan(0);
      }
    }
  });

  it("defines every severity colour on every theme", () => {
    const severities = ["critical", "high", "medium", "low", "informational"] as const;
    for (const theme of Object.values(themes)) {
      for (const sev of severities) {
        expect(typeof theme.severityColors[sev]).toBe("string");
        expect(theme.severityColors[sev].length).toBeGreaterThan(0);
      }
    }
  });
});

describe("getTheme", () => {
  it("returns the named theme when it exists", () => {
    expect(getTheme("light").name).toBe("light");
    expect(getTheme("solarized").name).toBe("solarized");
    expect(getTheme("dark").name).toBe("dark");
  });

  it("falls back to the default theme on unknown names", () => {
    expect(getTheme("does-not-exist")).toBe(DEFAULT_THEME);
    expect(getTheme(undefined)).toBe(DEFAULT_THEME);
    expect(getTheme("")).toBe(DEFAULT_THEME);
  });
});

describe("loadTheme", () => {
  async function writeConfig(body: string): Promise<void> {
    const target = configFilePath();
    await fs.mkdir(join(target, ".."), { recursive: true });
    await fs.writeFile(target, body, "utf8");
  }

  it("returns the default theme when no config file exists", () => {
    const t = loadTheme();
    expect(t.name).toBe("dark");
  });

  it("respects the theme key from config.toml", async () => {
    await writeConfig(`theme = "light"\n`);
    expect(loadTheme().name).toBe("light");
    await writeConfig(`theme = "solarized"\n`);
    expect(loadTheme().name).toBe("solarized");
  });

  it("falls back to default when config names an unknown theme", async () => {
    await writeConfig(`theme = "midnight"\n`);
    expect(loadTheme().name).toBe("dark");
  });
});
