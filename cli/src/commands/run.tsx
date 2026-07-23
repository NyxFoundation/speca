/**
 * `speca run` — pipeline dashboard command (M3).
 *
 * Spawns `uv run python3 scripts/run_phase.py --json …`, feeds the NDJSON
 * stream + per-phase log tail into a PipelineStore, and renders the
 * dashboard via Ink.
 *
 * Two modes:
 *   - TTY + no `--no-tui` / `--json` ⇒ Ink dashboard (this file).
 *   - non-TTY OR `--no-tui` OR `--json` ⇒ pass-through stream (M6).
 *     `--json` is reserved for M6 but we already pre-parse the stream so
 *     consumers can rely on the same NDJSON line-level contract.
 */
import { resolve } from "node:path";
import { render } from "ink";
import { createElement } from "react";

import { Dashboard } from "../components/Dashboard.js";
import { detectExpiredAuth, detectStaleResume } from "../lib/checks/preflight.js";
import { reportStderrError } from "../lib/errors/report.js";
import { emitJson, getOutputMode, printNoTui } from "../lib/io/output-mode.js";
import type { PipelineEvent } from "../lib/pipeline/events.js";
import { startLogWatcher } from "../lib/pipeline/log-watcher.js";
import { isKnownPhaseId, KNOWN_PHASE_IDS } from "../lib/pipeline/phase-names.js";
import { spawnPipeline, type SpawnPipelineOptions } from "../lib/pipeline/spawn.js";
import { validateRuntime } from "../lib/providers/registry.js";
import { PipelineStore } from "../lib/pipeline/store.js";
import { ThemeProvider } from "../lib/theme/index.js";
import { assertNever } from "../lib/util/assertNever.js";

export interface RunCommandFlags {
  phase?: string[];
  target?: string;
  workers?: number;
  maxConcurrent?: number;
  force?: boolean;
  budget?: number;
  noTui?: boolean;
  json?: boolean;
  outputDir?: string;
  /** Model runtime id (issue #113) — see src/lib/providers/registry.ts. */
  runtime?: string;
}

const HELP_TEXT = `\
speca run — execute SPECA pipeline phases with a live dashboard

Usage
  $ speca run --phase <id...>           Run one or more phases by id
  $ speca run --target <id>             Run all dependencies up to <id>

Flags
  --phase <id...>            Phase ids (e.g. --phase 01a 01b)
  --target <id>              Run dependency chain up to <id>
  --workers <N>              Worker count (default 4)
  --max-concurrent <N>       Max concurrent Claude executions (default 8)
  --force                    Ignore resume state, re-run everything
  --runtime <id>             Model runtime: claude (default) | api | codex |
                             gemini | ollama | copilot. Credentials are
                             checked up front (e.g. ollama cloud needs
                             OLLAMA_API_KEY); forwarded to the orchestrator
                             as run_phase.py --runtime <id>.
  --budget <usd>             Cost cap (forwarded to orchestrator when supported)
  --output-dir <path>        Output directory (sets SPECA_OUTPUT_DIR)
  --no-tui                   Force plain-text pass-through (M6)
  --json                     Emit raw NDJSON events on stdout (M6)
  --help, -h                 Show this help

Examples
  $ speca run --phase 01a
  $ speca run --target 03 --workers 4 --max-concurrent 8
  $ speca run --phase 01b --force
  $ speca run --target 03 --runtime ollama    # ollama cloud instead of claude
`;

export function printRunHelp(): void {
  process.stdout.write(HELP_TEXT);
}

interface RunOptions {
  flags: RunCommandFlags;
  cwd?: string;
  /** Test seam — defaults to spawning `uv run python3 scripts/run_phase.py`. */
  spawn?: typeof spawnPipeline;
  /** Test seam — defaults to chokidar log watcher. */
  startLogs?: typeof startLogWatcher;
  /** Test seam — override the auth.json path consulted by pre-flight. */
  authFile?: string;
  /** Test seam — disable pre-flight checks entirely. */
  skipPreflight?: boolean;
}

function parsePhaseList(raw: unknown): string[] | undefined {
  if (raw === undefined) return undefined;
  if (typeof raw === "string") return raw.split(",").map((s) => s.trim()).filter(Boolean);
  if (Array.isArray(raw)) return raw.map(String).filter(Boolean);
  return undefined;
}

/**
 * Warn (don't reject) when the user passes a phase id the CLI doesn't
 * know about. Forks may legitimately add new phases via custom orchestrator
 * configs, so we forward the unknown id to the Python side and let the
 * orchestrator emit `phase-failed` if it really is bogus.
 */
function warnUnknownPhases(ids: string[]): void {
  const unknown = ids.filter((id) => !isKnownPhaseId(id));
  if (unknown.length === 0) return;
  process.stderr.write(
    `[speca run] warning: phase id(s) not in the canonical set: ${unknown.join(", ")}\n` +
      `  Known: ${KNOWN_PHASE_IDS.join(", ")}\n` +
      "  Continuing — the orchestrator will emit phase-failed if these are unknown to it too.\n",
  );
}

/**
 * Headless / pass-through mode. Used for `--no-tui`, `--json`, and when
 * stdout is not a TTY. We forward stderr to our stderr and (for `--json`)
 * stdout NDJSON lines verbatim. The TUI dashboard is bypassed.
 */
async function runHeadless(
  opts: RunOptions,
  spawnOpts: SpawnPipelineOptions,
  mode: "json" | "no-tui",
): Promise<number> {
  const spawnFn = opts.spawn ?? spawnPipeline;
  const handle = spawnFn(spawnOpts);
  handle.on("event", (event) => {
    if (mode === "json") {
      // Use M6 emitJson helper so the envelope (`ts` stamp, error fallback)
      // matches every other subcommand's NDJSON output. The event already
      // has a ts from the orchestrator; emitJson preserves it.
      emitJson(event as unknown as Record<string, unknown>);
    } else {
      const summary = formatEventSummary(event);
      if (summary) printNoTui(summary);
    }
  });
  handle.on("warn", (failure) => {
    process.stderr.write(`[speca run] warn: ${failure.reason}\n`);
  });
  handle.on("stderr", (line) => {
    process.stderr.write(line + "\n");
  });
  handle.on("spawn-error", (err) => {
    reportStderrError("subprocess-crash", {
      message: `failed to spawn orchestrator: ${err.message}`,
    });
  });
  return handle.done;
}

export function formatEventSummary(event: PipelineEvent): string {
  switch (event.type) {
    case "pipeline-started":
      return `[pipeline] started: phases=${JSON.stringify(event.phases)}`;
    case "pipeline-completed":
      return `[pipeline] completed in ${event.duration_s.toFixed(2)}s`;
    case "phase-started":
      return `[${event.phase}] started (workers=${event.workers}, max-concurrent=${event.max_concurrent})`;
    case "phase-completed":
      return `[${event.phase}] done (${event.total_results} results, ${event.duration_s.toFixed(2)}s)`;
    case "phase-failed":
      return `[${event.phase}] FAILED: ${event.reason}`;
    case "budget-exceeded":
      return `[${event.phase}] BUDGET EXCEEDED: $${event.cost_usd ?? 0} / $${event.max_budget_usd ?? 0}`;
    case "circuit-breaker-tripped":
      return `[${event.phase}] CIRCUIT BREAKER TRIPPED: ${event.reason}`;
    case "warning":
      return `[${event.phase}] WARNING: ${event.message}`;
    default:
      return assertNever(event, "formatEventSummary");
  }
}

export async function runRunCommand(opts: RunOptions): Promise<number> {
  const phases = parsePhaseList(opts.flags.phase as unknown);
  if (!phases?.length && !opts.flags.target) {
    process.stderr.write("speca run: must pass --phase <id...> or --target <id>\n");
    process.stderr.write(HELP_TEXT);
    return 2;
  }
  if (phases?.length) warnUnknownPhases(phases);
  if (opts.flags.target && !isKnownPhaseId(opts.flags.target)) {
    warnUnknownPhases([opts.flags.target]);
  }

  const cwd = opts.cwd ?? process.cwd();
  const outputDir = opts.flags.outputDir ? resolve(cwd, opts.flags.outputDir) : undefined;

  // Runtime selection (issue #113). Validate the id and its credentials
  // against the ProviderRegistry BEFORE spawning, so `--runtime ollama`
  // without OLLAMA_API_KEY fails in milliseconds with a fix hint instead
  // of burning a pipeline start. No flag = orchestrator default (claude).
  const runtime = opts.flags.runtime;
  if (runtime !== undefined) {
    const check = validateRuntime(runtime);
    if (!check.ok) {
      for (const line of check.messages) {
        process.stderr.write(`speca run: ${line}\n`);
      }
      return 2;
    }
  }

  // Pre-flight checks. Each detector returns null when clean; a non-null
  // failure short-circuits here with the matching ErrorKind. Callers can
  // disable with `skipPreflight: true` (used by tests that aren't
  // exercising this path).
  if (!opts.skipPreflight) {
    // The expired-auth detector inspects the claude CLI's credential
    // store — only meaningful when claude is the runtime that will run.
    if (runtime === undefined || runtime === "claude") {
      const expiredAuth = await detectExpiredAuth({ authFile: opts.authFile });
      if (expiredAuth) {
        return reportStderrError("auth-expired", expiredAuth);
      }
    }
    if (!opts.flags.force) {
      const stale = await detectStaleResume({
        cwd,
        force: false,
        outputDir,
      });
      if (stale) {
        return reportStderrError("stale-resume", stale);
      }
    }
  }
  const spawnOpts: SpawnPipelineOptions = {
    phases,
    target: opts.flags.target,
    workers: opts.flags.workers,
    maxConcurrent: opts.flags.maxConcurrent,
    force: opts.flags.force,
    outputDir,
    cwd,
    budget: opts.flags.budget,
    runtime,
  };

  const outputMode = getOutputMode({ noTui: opts.flags.noTui, json: opts.flags.json });
  if (outputMode !== "tui") {
    return runHeadless(opts, spawnOpts, outputMode);
  }

  // TUI mode.
  const store = new PipelineStore();
  if (opts.flags.budget != null) {
    store.setBudget(opts.flags.budget);
  }

  const spawnFn = opts.spawn ?? spawnPipeline;
  const handle = spawnFn(spawnOpts);
  handle.on("event", (event) => store.applyEvent(event));
  handle.on("warn", (failure) => {
    // Surface in stderr without spamming the TUI.
    process.stderr.write(`[speca run] warn: ${failure.reason}\n`);
  });
  handle.on("stderr", () => {
    // Decorative orchestrator output is suppressed in TUI mode to avoid
    // clobbering Ink's renderer. The dashboard derives its state from
    // events and the log file tail.
  });
  handle.on("spawn-error", (err) => {
    reportStderrError("subprocess-crash", {
      message: `failed to spawn orchestrator: ${err.message}`,
    });
  });

  const startLogs = opts.startLogs ?? startLogWatcher;
  const logRoot = outputDir ? resolve(outputDir, "logs") : resolve(cwd, "outputs", "logs");
  let stopLogs: (() => Promise<void>) | null = null;
  try {
    stopLogs = await startLogs({
      dir: logRoot,
      onLine: (line) => store.applyLog(line),
      onWarn: (msg) => process.stderr.write(`[speca run] log-watcher: ${msg}\n`),
    });
  } catch (err) {
    process.stderr.write(`[speca run] log-watcher unavailable: ${(err as Error).message}\n`);
  }

  const app = render(
    createElement(ThemeProvider, null, createElement(Dashboard, { store, handle, cwd })),
  );
  const exitCode = await handle.done;
  await app.waitUntilExit();
  await stopLogs?.();
  return exitCode;
}
