/**
 * Error-modal taxonomy. Mirrors the seven failure modes enumerated in
 * `docs/SPECA_CLI_SPEC.md` §10.4 (plus a generic `unknown` bucket so
 * callers always have a safe fallback).
 *
 * Each kind ships:
 *   - `severity` — drives the icon colour through `Theme.colors`.
 *   - `icon` — a single ASCII glyph paired with the colour, so the modal
 *     stays readable under `NO_COLOR=1` (SPEC §10.8 accessibility).
 *   - `defaultTitle` — the title shown when the caller does not pass one.
 *   - `defaultHint` — the recovery hint shown when the caller does not
 *     pass one.
 *
 * No human-facing strings outside this file; localisation happens here when
 * `i18n.ts` lands (SPEC §10.7).
 */

export type ErrorKind =
  | "pipeline-failure"
  | "auth-expired"
  | "budget-exceeded"
  | "circuit-broken"
  | "schema-mismatch"
  | "stale-resume"
  | "subprocess-crash"
  | "unknown";

export type ErrorSeverity = "error" | "warn" | "info";

export interface ErrorKindMeta {
  severity: ErrorSeverity;
  /** ASCII glyph shown to the left of the title (single column). */
  icon: string;
  defaultTitle: string;
  defaultHint: string;
}

export const ERROR_KINDS: Record<ErrorKind, ErrorKindMeta> = {
  "pipeline-failure": {
    severity: "error",
    icon: "x",
    defaultTitle: "Pipeline failure",
    defaultHint: "Inspect the log pane and retry the failed phase, or run `speca run --resume`.",
  },
  "auth-expired": {
    severity: "warn",
    icon: "!",
    defaultTitle: "Authentication expired",
    defaultHint: "Run `speca auth login` to re-authenticate, then resume the run.",
  },
  "budget-exceeded": {
    severity: "warn",
    icon: "$",
    defaultTitle: "Budget exceeded",
    defaultHint: "Bump the cap and resume, or reduce the worker count and retry.",
  },
  "circuit-broken": {
    severity: "error",
    icon: "/",
    defaultTitle: "Circuit breaker tripped",
    defaultHint:
      "Too many consecutive failures. Check the upstream service and re-run with `--force` once it recovers.",
  },
  "schema-mismatch": {
    severity: "error",
    icon: "?",
    defaultTitle: "Schema mismatch",
    defaultHint: "Re-run `npm run sync-schemas` and re-export the upstream JSON Schema.",
  },
  "stale-resume": {
    severity: "warn",
    icon: "~",
    defaultTitle: "Stale resume state",
    defaultHint: "Run with `--force` to clear the existing partials and start over.",
  },
  "subprocess-crash": {
    severity: "error",
    icon: "x",
    defaultTitle: "Subprocess crashed",
    defaultHint: "Check the log pane for the child-process exit code, then retry the failed phase.",
  },
  unknown: {
    severity: "error",
    icon: "x",
    defaultTitle: "Unexpected error",
    defaultHint: "See the log pane for details. File an issue if it reproduces.",
  },
};

export function getErrorKindMeta(kind: ErrorKind): ErrorKindMeta {
  return ERROR_KINDS[kind] ?? ERROR_KINDS.unknown;
}
