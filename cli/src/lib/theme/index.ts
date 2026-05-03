/**
 * Theme registry + React Context binding for `speca-cli`.
 *
 * Three themes ship in v1: `dark` (default), `light`, and `solarized`. Users
 * select one via `~/.config/speca/config.toml`:
 *
 *   theme = "dark"
 *
 * Components consume the active theme via the `useTheme()` hook. A component
 * mounted outside a `<ThemeProvider>` falls back to the dark theme — that
 * way standalone unit tests do not need to wrap every render in a provider.
 */

import { createContext, createElement, useContext, type ReactNode } from "react";
import { loadUserConfig } from "../config/index.js";
import { darkTheme } from "./themes/dark.js";
import { lightTheme } from "./themes/light.js";
import { solarizedTheme } from "./themes/solarized.js";
import type { Theme } from "./types.js";

export type { Theme, ThemeColors, SeverityName } from "./types.js";

/** All themes built into speca-cli, keyed by `theme.name`. */
export const themes: Record<string, Theme> = {
  dark: darkTheme,
  light: lightTheme,
  solarized: solarizedTheme,
};

/** The default theme used when nothing is configured / a bad name is set. */
export const DEFAULT_THEME: Theme = darkTheme;

/**
 * Look up a theme by name. Unknown names fall back to the default rather
 * than throwing, so a typo in the user's config does not crash the CLI.
 */
export function getTheme(name: string | undefined): Theme {
  if (!name) return DEFAULT_THEME;
  const theme = themes[name];
  return theme ?? DEFAULT_THEME;
}

/**
 * Read the user's config and return the resolved Theme. Pure-ish — calls
 * `loadUserConfig()` which touches disk synchronously. Cheap enough to call
 * once per process at startup.
 */
export function loadTheme(): Theme {
  const cfg = loadUserConfig();
  return getTheme(cfg.theme);
}

const ThemeContext = createContext<Theme>(DEFAULT_THEME);
ThemeContext.displayName = "SpecaThemeContext";

export { ThemeContext };

interface ThemeProviderProps {
  theme?: Theme;
  children: ReactNode;
}

/**
 * Provider that injects a Theme into the React tree. Pass `theme` explicitly
 * for tests; otherwise the active theme is loaded from disk.
 */
export function ThemeProvider({ theme, children }: ThemeProviderProps) {
  const value = theme ?? loadTheme();
  return createElement(ThemeContext.Provider, { value }, children);
}

/**
 * Hook returning the active Theme. Outside a provider this returns the
 * default (dark) theme so component renders never crash.
 */
export function useTheme(): Theme {
  return useContext(ThemeContext);
}
