// Filter DSL parser & matcher — mirrors the small query language documented
// in SPECA_CLI_SPEC §5.4.1.
//
// Goals:
//   - feel like a search box: free text on the left, structured filters on
//     the right (`severity:high`, `verdict:CONFIRMED_VULNERABILITY`, …)
//   - keep it dumb: a single regex pass over whitespace-separated tokens
//   - tolerate user typos quietly — unknown keys fall back to free text
//     instead of erroring, so the input never blocks the user mid-typing
//   - case-insensitive on values; severity / verdict normalise to the
//     canonical casing used elsewhere in the SPA
//
// The DSL accepts:
//   severity:HIGH                 → exact severity match
//   severity:high|critical        → OR-list (pipe-separated)
//   verdict:CONFIRMED_VULNERABILITY
//   prop:PROP-6a4*                → glob (`*` and `?`) on property_id
//   repo:lighthouse_fusaka        → glob match on the finding's `target`
//                                   (the client/target directory), falling
//                                   back to `run_id` when a finding carries
//                                   no target (single-target layout)
//   path:contracts/**/*.sol       → glob on the finding's `file` field.
//                                   `**` matches any number of path
//                                   segments. Mirrors CLI spec §3.5
//                                   `speca browse [glob]`.
//   any unquoted free token       → AND-combined substring search across
//                                   property_id / file / proof_trace /
//                                   evidence_snippet / reviewer_notes
//
// Tokens may be combined with spaces; combination is AND. Empty input
// returns an "accept all" predicate.

import { SEVERITY_LEVELS, KNOWN_VERDICTS, type Finding, type Severity } from "./types";

export type DslKey = "severity" | "verdict" | "prop" | "repo" | "path";

export interface ParsedFilter {
  /** Raw input the user typed, kept for echo / re-render. */
  raw: string;
  /** Severity values to allow (OR). Empty array = no severity filter. */
  severity: Severity[];
  /** Verdict values to allow (OR). Case preserved. */
  verdict: string[];
  /** `prop:` globs. Each entry is a regex pre-compiled from the glob. */
  propPatterns: RegExp[];
  /** `repo:` globs (matched against the finding's `target`, or `run_id`
   * when the finding has no target). */
  repoPatterns: RegExp[];
  /** `path:` globs (matched against the finding's `file` field). */
  pathPatterns: RegExp[];
  /** Free-text tokens. AND-combined, case-insensitive substring. */
  freeTokens: string[];
  /** Tokens the parser could not interpret as a key:value — kept so the
   * UI can surface a "Unknown filter key" hint without breaking the
   * user's typing. */
  unknownKeys: string[];
}

const KNOWN_KEYS: ReadonlySet<DslKey> = new Set([
  "severity",
  "verdict",
  "prop",
  "repo",
  "path",
]);

const SEVERITY_LOOKUP: Record<string, Severity> = (() => {
  const out: Record<string, Severity> = {};
  for (const sev of SEVERITY_LEVELS) {
    out[sev.toLowerCase()] = sev;
  }
  return out;
})();

const VERDICT_LOOKUP: Record<string, string> = (() => {
  const out: Record<string, string> = {};
  for (const v of KNOWN_VERDICTS) {
    out[v.toLowerCase()] = v;
  }
  return out;
})();

/**
 * Tokenise on whitespace, preserving `key:value` pairs verbatim. We do
 * not support quoted strings yet — v0 datasets are small enough that
 * single-word free text matches everything users have asked for so far.
 */
function tokenise(input: string): string[] {
  return input
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length > 0);
}

/** Convert a shell-style glob (`*`, `?`) into an anchored regex. */
function globToRegExp(glob: string): RegExp {
  const escaped = glob.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  const pattern = escaped.replace(/\*/g, ".*").replace(/\?/g, ".");
  return new RegExp(`^${pattern}$`, "i");
}

/** Convert a path-style glob into an anchored regex.
 *
 * Same as :func:`globToRegExp` except ``**`` matches any number of path
 * segments (including zero) and a single ``*`` is restricted to one
 * segment. This mirrors the behaviour of `git ls-files`, fnmatch, and
 * the SPECA CLI's `speca browse <glob>` shell pattern. */
function pathGlobToRegExp(glob: string): RegExp {
  // Escape regex metacharacters, then substitute glob constructs. Order
  // matters: `**` must be translated before `*` so the longer match wins.
  const escaped = glob.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  const pattern = escaped
    .replace(/\*\*/g, "::DOUBLESTAR::")
    .replace(/\*/g, "[^/]*")
    .replace(/\?/g, "[^/]")
    .replace(/::DOUBLESTAR::/g, ".*");
  return new RegExp(`^${pattern}$`, "i");
}

export function parseFilterDsl(input: string): ParsedFilter {
  const result: ParsedFilter = {
    raw: input,
    severity: [],
    verdict: [],
    propPatterns: [],
    repoPatterns: [],
    pathPatterns: [],
    freeTokens: [],
    unknownKeys: [],
  };
  if (!input || !input.trim()) return result;

  for (const token of tokenise(input)) {
    const colonAt = token.indexOf(":");
    // A bare ":" or trailing ":" looks like a half-typed key — treat the
    // whole token as free text so the user can keep typing without the
    // UI flicker-filtering on an incomplete query.
    if (colonAt <= 0 || colonAt === token.length - 1) {
      result.freeTokens.push(token);
      continue;
    }
    const key = token.slice(0, colonAt).toLowerCase();
    const rawValue = token.slice(colonAt + 1);
    if (!KNOWN_KEYS.has(key as DslKey)) {
      result.unknownKeys.push(key);
      result.freeTokens.push(token);
      continue;
    }
    const values = rawValue.split("|").filter((v) => v.length > 0);
    if (values.length === 0) continue;

    switch (key as DslKey) {
      case "severity":
        for (const v of values) {
          const sev = SEVERITY_LOOKUP[v.toLowerCase()];
          if (sev) result.severity.push(sev);
        }
        break;
      case "verdict":
        for (const v of values) {
          // Accept either canonical (CONFIRMED_VULNERABILITY) or
          // shorthand lowercased. Unknown forks pass through verbatim
          // so a custom verdict-name in PARTIALs still matches.
          const canonical = VERDICT_LOOKUP[v.toLowerCase()] ?? v;
          result.verdict.push(canonical);
        }
        break;
      case "prop":
        for (const v of values) {
          result.propPatterns.push(globToRegExp(v));
        }
        break;
      case "repo":
        for (const v of values) {
          result.repoPatterns.push(globToRegExp(v));
        }
        break;
      case "path":
        for (const v of values) {
          result.pathPatterns.push(pathGlobToRegExp(v));
        }
        break;
    }
  }
  return result;
}

/** Is `f` allowed under `parsed`? Empty / all-empty parsed → always `true`. */
export function matchFilter(f: Finding, parsed: ParsedFilter): boolean {
  if (parsed.severity.length > 0 && !parsed.severity.includes(f.severity)) {
    return false;
  }
  if (parsed.verdict.length > 0) {
    if (!f.verdict) return false;
    if (!parsed.verdict.includes(f.verdict)) return false;
  }
  if (parsed.propPatterns.length > 0) {
    if (!parsed.propPatterns.some((re) => re.test(f.property_id))) {
      return false;
    }
  }
  if (parsed.repoPatterns.length > 0) {
    // Prefer the real client/target; fall back to run_id for single-target
    // findings that carry no target.
    const repoHaystack = f.target ?? f.run_id;
    if (!parsed.repoPatterns.some((re) => re.test(repoHaystack))) {
      return false;
    }
  }
  if (parsed.pathPatterns.length > 0) {
    // No file path → definitely not a match for a `path:` constraint.
    if (!f.file) return false;
    if (!parsed.pathPatterns.some((re) => re.test(f.file as string))) {
      return false;
    }
  }
  if (parsed.freeTokens.length > 0) {
    const haystackParts = [
      f.property_id,
      f.file ?? "",
      f.proof_trace ?? "",
      f.evidence_snippet ?? "",
      f.reviewer_notes ?? "",
    ];
    const haystack = haystackParts.join("\n").toLowerCase();
    for (const token of parsed.freeTokens) {
      if (!haystack.includes(token.toLowerCase())) return false;
    }
  }
  return true;
}

/** Is `parsed` effectively empty (i.e. accepts everything)? */
export function isEmptyFilter(parsed: ParsedFilter): boolean {
  return (
    parsed.severity.length === 0 &&
    parsed.verdict.length === 0 &&
    parsed.propPatterns.length === 0 &&
    parsed.repoPatterns.length === 0 &&
    parsed.pathPatterns.length === 0 &&
    parsed.freeTokens.length === 0
  );
}
