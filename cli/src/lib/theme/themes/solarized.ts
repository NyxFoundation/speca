/**
 * Solarized theme. Ink uses Chalk-style colour names; we map Solarized's
 * 16-colour palette to the closest Chalk identifiers. Terminals configured
 * with the Solarized palette will render the canonical colours; others get a
 * reasonable approximation.
 *
 * Reference: https://ethanschoonover.com/solarized/
 */

import type { Theme } from "../types.js";

export const solarizedTheme: Theme = {
  name: "solarized",
  colors: {
    // Solarized base colours map onto Chalk's standard ANSI names.
    primary: "blue", // base02-friendly accent
    secondary: "magenta", // violet
    success: "green",
    warn: "yellow",
    error: "red",
    info: "cyan",
    dim: "gray",
    text: "white",
    muted: "gray",
    border: "gray",
  },
  severityColors: {
    critical: "red",
    high: "magenta",
    medium: "yellow",
    low: "cyan",
    informational: "gray",
  },
};
