/**
 * Cross-cutting output-mode helpers shared by every subcommand.
 *
 * Three output modes are supported (SPEC §6, §10):
 *
 *   - `tui`       Interactive Ink rendering (default when stdout is a TTY).
 *   - `no-tui`    Plain-text line-by-line output. Forced by `--no-tui` or
 *                 by a non-TTY stdout (CI, pipes). Override with the
 *                 `SPECA_FORCE_TUI=1` env var when you really want to keep
 *                 the TUI under a pipe (e.g. `tee` capture during dev).
 *   - `json`      One JSON object per line on stdout (NDJSON). Implies
 *                 `no-tui`. Caller-side schemas are documented per
 *                 subcommand; this layer only enforces the envelope:
 *                 `{ type: string, ts: string, ... }`.
 *
 * Callers do **not** have to opt in beyond reading their own `--no-tui` /
 * `--json` flags — `getOutputMode(flags)` consolidates the decision so a
 * future tweak (e.g. honouring `NO_COLOR=1`) lives in one place.
 */

export type OutputMode = "tui" | "no-tui" | "json";

export interface OutputModeFlags {
  noTui?: boolean;
  json?: boolean;
}

export interface OutputModeEnv {
  isTTY?: boolean;
  /** Set `SPECA_FORCE_TUI=1` to keep the TUI even when stdout is not a TTY. */
  forceTui?: boolean;
}

function readEnv(): OutputModeEnv {
  return {
    isTTY: Boolean(process.stdout.isTTY),
    forceTui: process.env.SPECA_FORCE_TUI === "1",
  };
}

/**
 * Resolve the active output mode from CLI flags + the runtime environment.
 * Decision order:
 *
 *   1. `--json` always wins. Output is NDJSON regardless of TTY.
 *   2. `--no-tui` forces plain-text output even on a TTY.
 *   3. Non-TTY stdout falls back to `no-tui` (unless `SPECA_FORCE_TUI=1`).
 *   4. Otherwise: `tui`.
 *
 * The `env` parameter is exposed so unit tests can drive the decision
 * without mucking with `process.stdout`.
 */
export function getOutputMode(
  flags: OutputModeFlags = {},
  env: OutputModeEnv = readEnv(),
): OutputMode {
  if (flags.json) return "json";
  if (flags.noTui) return "no-tui";
  if (env.forceTui) return "tui";
  if (env.isTTY === false) return "no-tui";
  return "tui";
}

/**
 * Print a single line on stdout for `no-tui` mode. Trailing newline is
 * always added so callers can pass templated strings without worrying
 * about line termination.
 */
export function printNoTui(text: string): void {
  process.stdout.write(`${text}\n`);
}

/**
 * Emit a single NDJSON record on stdout. The caller is responsible for
 * the `type` discriminator; this helper enforces the envelope shape and
 * stamps a `ts` field if one isn't present (RFC 3339 / ISO 8601).
 *
 * Records that fail to serialise (cycles, bigint, etc) fall back to a
 * `{ type: "error", ts, error: "..." }` envelope so consumers always see
 * one valid line per call.
 */
export function emitJson(record: Record<string, unknown>): void {
  const stamped = { ts: record.ts ?? new Date().toISOString(), ...record };
  let line: string;
  try {
    line = JSON.stringify(stamped);
  } catch (err) {
    const fallback = {
      type: "error",
      ts: new Date().toISOString(),
      error: `emitJson: failed to serialise record (${(err as Error).message})`,
    };
    line = JSON.stringify(fallback);
  }
  process.stdout.write(`${line}\n`);
}
