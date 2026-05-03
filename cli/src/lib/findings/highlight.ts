/**
 * highlight.ts — small wrapper around `cli-highlight` that swallows errors
 * (unknown language, malformed source, terminal w/o color) and returns the
 * original text on failure.  cli-highlight ships as CJS; we import the named
 * export which works under TS+esm thanks to `esModuleInterop`.
 */
import { highlight as ansiHighlight } from "cli-highlight";

export interface HighlightOptions {
  language?: string;
  /** When true, force-disable ANSI escapes (used by tests). */
  plain?: boolean;
}

export function highlightCode(source: string, options: HighlightOptions = {}): string {
  if (options.plain) return source;
  try {
    return ansiHighlight(source, {
      language: options.language,
      ignoreIllegals: true,
    });
  } catch {
    return source;
  }
}
