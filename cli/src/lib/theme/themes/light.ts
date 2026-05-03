/**
 * Light theme — designed for light terminal backgrounds. Avoids the
 * `*Bright` variants because they tend to wash out against white.
 */

import type { Theme } from "../types.js";

export const lightTheme: Theme = {
  name: "light",
  colors: {
    primary: "blue",
    secondary: "magenta",
    success: "green",
    warn: "yellow",
    error: "red",
    info: "cyan",
    dim: "gray",
    text: "black",
    muted: "gray",
    border: "gray",
  },
  severityColors: {
    critical: "red",
    high: "magenta",
    medium: "yellow",
    low: "blue",
    informational: "gray",
  },
};
