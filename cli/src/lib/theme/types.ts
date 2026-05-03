/**
 * Theme primitives. All colour values are Chalk-style identifiers passed
 * straight through to Ink's `<Text color="...">` prop. Restricting the type
 * to `string` (rather than a union of every Chalk literal) keeps custom
 * themes possible without losing autocomplete on the well-known names.
 */

export type SeverityName =
  | "critical"
  | "high"
  | "medium"
  | "low"
  | "informational";

export interface ThemeColors {
  /** Primary accent — used for headings, focused borders, the doctor table. */
  primary: string;
  /** Secondary accent — used for hints / informative non-error text. */
  secondary: string;
  /** Status: success / OK. */
  success: string;
  /** Status: warning / non-fatal issue. */
  warn: string;
  /** Status: error / failure. */
  error: string;
  /** Status: informational / neutral. */
  info: string;
  /** Dim text (deprioritised lines). */
  dim: string;
  /** Default body text colour. */
  text: string;
  /** Muted variant of body text — captions, footers. */
  muted: string;
  /** Border / frame colour. */
  border: string;
}

export interface Theme {
  name: string;
  colors: ThemeColors;
  severityColors: Record<SeverityName, string>;
}
