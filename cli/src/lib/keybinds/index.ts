/**
 * Action-based keybinds layer for speca-cli.
 *
 * Components subscribe to abstract `action` strings rather than raw key
 * codes:
 *
 *   useKeybind("exit", () => app.exit());
 *   useKeybind("toggle-log", () => setShowLog((v) => !v));
 *
 * The mapping `action -> [key, ...]` comes from `config.toml`'s
 * `[keybinds]` table, with `DEFAULT_KEYBINDS` providing every fallback.
 * User overrides win on a per-action basis (an unknown action name in the
 * config is dropped silently; an action absent from the config keeps its
 * default).
 *
 * The `useInput` integration is intentionally one-hook-per-`useKeybind`
 * call. Ink's `useInput` is cheap (just appends a stdin listener) and
 * keeping each subscription isolated avoids the "did this handler need to
 * stop propagation?" problem that comes with a global dispatcher.
 */

import { useInput } from "ink";
import { useMemo } from "react";
import { loadUserConfig, type UserConfig } from "../config/index.js";
import { DEFAULT_KEYBINDS } from "./defaults.js";
import { matchAny, type KeyEvent } from "./match.js";

export { DEFAULT_KEYBINDS } from "./defaults.js";
export { matchKey, matchAny, type KeyEvent } from "./match.js";

export type KeybindMap = Record<string, string[]>;

/**
 * Merge the user's overrides on top of the defaults. Each action keeps its
 * default unless the user has provided a non-empty array for that action.
 */
export function resolveKeybinds(userOverrides: KeybindMap = {}): KeybindMap {
  const result: KeybindMap = {};
  for (const [action, keys] of Object.entries(DEFAULT_KEYBINDS)) {
    result[action] = keys.slice();
  }
  for (const [action, keys] of Object.entries(userOverrides)) {
    if (Array.isArray(keys) && keys.length > 0) {
      result[action] = keys.slice();
    }
  }
  return result;
}

let cachedConfig: UserConfig | undefined;
let cachedMap: KeybindMap | undefined;

/**
 * Lazily loads `config.toml` once per process and caches the resolved
 * keybind map. Call `resetKeybindCache()` between test cases that mutate
 * `~/.config/speca/config.toml` directly.
 */
export function getActiveKeybinds(): KeybindMap {
  if (cachedMap) return cachedMap;
  cachedConfig = loadUserConfig();
  cachedMap = resolveKeybinds(cachedConfig.keybinds);
  return cachedMap;
}

export function resetKeybindCache(): void {
  cachedConfig = undefined;
  cachedMap = undefined;
}

/**
 * Look up the active key descriptors for `action`. Returns `[]` when the
 * action is unknown (neither a default nor a user override).
 */
export function keysForAction(action: string, overrides?: KeybindMap): string[] {
  const map = overrides ?? getActiveKeybinds();
  return map[action] ?? [];
}

/**
 * React hook: invoke `handler` whenever the user presses any key bound to
 * `action`. Pass `isActive: false` to temporarily suspend the binding (e.g.
 * while a modal owns input focus).
 */
export function useKeybind(
  action: string,
  handler: () => void,
  options: { isActive?: boolean } = {},
): void {
  const isActive = options.isActive ?? true;
  const descriptors = useMemo(() => keysForAction(action), [action]);
  useInput(
    (input, key) => {
      if (matchAny(descriptors, input, key as KeyEvent)) {
        handler();
      }
    },
    { isActive },
  );
}
