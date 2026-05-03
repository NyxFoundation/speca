/**
 * User config loader for speca-cli.
 *
 * Path layout (mirrors `src/auth/store.ts::authFilePath`):
 *   POSIX:    $XDG_CONFIG_HOME/speca/config.toml  (fallback ~/.config/speca/config.toml)
 *   Windows:  %APPDATA%\speca\config.toml
 *
 * The file is intentionally TOML so users can hand-edit it with comments.
 * Example:
 *
 *   theme = "dark"
 *
 *   [keybinds]
 *   exit = ["q", "ctrl+c"]
 *   toggle-log = ["l"]
 *
 * Parse failures (missing file, bad TOML, wrong types) all degrade to the
 * default config — the CLI must not refuse to launch because config.toml is
 * malformed. Misconfiguration is surfaced via `speca doctor` (a future M6
 * extension; not in scope for this PR).
 */

import { readFileSync } from "node:fs";
import { homedir, platform } from "node:os";
import { join } from "node:path";
import { parse as parseToml } from "smol-toml";

export interface UserConfig {
  /** Theme name (looked up against `themes` in `lib/theme`). */
  theme: string;
  /**
   * `actionName -> [key, key, ...]`. Keys are strings consumed by the
   * keybinds layer (`lib/keybinds`); a key may be a single character
   * (`"q"`), an Ink-style modifier name (`"escape"`, `"return"`, `"tab"`),
   * or a `ctrl+x` style chord.
   */
  keybinds: Record<string, string[]>;
}

const DEFAULT_CONFIG: UserConfig = {
  theme: "dark",
  keybinds: {},
};

/**
 * Resolve the absolute path to `config.toml` for the current OS. Pure
 * function; mirrors the resolution rules of `authFilePath()` so users only
 * have to remember one config dir.
 */
export function configFilePath(env: NodeJS.ProcessEnv = process.env): string {
  if (platform() === "win32") {
    const appData = env.APPDATA;
    const base = appData && appData.length > 0 ? appData : join(homedir(), "AppData", "Roaming");
    return join(base, "speca", "config.toml");
  }
  const xdg = env.XDG_CONFIG_HOME;
  const base = xdg && xdg.length > 0 ? xdg : join(homedir(), ".config");
  return join(base, "speca", "config.toml");
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((v) => typeof v === "string");
}

/**
 * Coerce a `parseToml` return value into a `UserConfig`. Anything that does
 * not match the expected shape is dropped silently and the default takes
 * over, so a partially-correct file still yields a usable config.
 */
function normalise(parsed: unknown): UserConfig {
  if (!parsed || typeof parsed !== "object") return { ...DEFAULT_CONFIG };
  const root = parsed as Record<string, unknown>;
  const theme = typeof root.theme === "string" && root.theme.length > 0 ? root.theme : DEFAULT_CONFIG.theme;

  const keybinds: Record<string, string[]> = {};
  if (root.keybinds && typeof root.keybinds === "object") {
    for (const [action, keys] of Object.entries(root.keybinds as Record<string, unknown>)) {
      if (isStringArray(keys)) {
        keybinds[action] = keys;
      }
    }
  }

  return { theme, keybinds };
}

/**
 * Load `~/.config/speca/config.toml` (or platform equivalent). Always
 * returns a valid `UserConfig`; missing / unreadable / malformed files all
 * yield the default. Synchronous because callers need it during React
 * provider construction.
 */
export function loadUserConfig(filePath: string = configFilePath()): UserConfig {
  let raw: string;
  try {
    raw = readFileSync(filePath, "utf8");
  } catch {
    return { ...DEFAULT_CONFIG };
  }
  let parsed: unknown;
  try {
    parsed = parseToml(raw);
  } catch {
    return { ...DEFAULT_CONFIG };
  }
  return normalise(parsed);
}
