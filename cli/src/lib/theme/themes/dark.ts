/**
 * Dark theme — designed for dark terminal backgrounds. This is the default
 * when no `theme` key is set in the user config.
 *
 * Severity colours follow the convention used elsewhere in SPECA outputs:
 *   critical → red, high → magenta, medium → yellow, low → cyan,
 *   informational → grey.
 */

import type { Theme } from "../types.js";

export const darkTheme: Theme = {
  name: "dark",
  colors: {
    primary: "cyanBright",
    secondary: "magentaBright",
    success: "greenBright",
    warn: "yellowBright",
    error: "redBright",
    info: "blueBright",
    dim: "gray",
    text: "white",
    muted: "gray",
    border: "gray",
  },
  severityColors: {
    critical: "redBright",
    high: "magentaBright",
    medium: "yellowBright",
    low: "cyanBright",
    informational: "gray",
  },
};
