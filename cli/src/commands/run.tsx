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
import { startLogWatcher } from "../lib/pipeline/log-watcher.js";
import { spawnPipeline, type SpawnPipelineOptions } from "../lib/pipeline/spawn.js";
import { PipelineStore } from "../lib/pipeline/store.js";

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
  --budget <usd>             Cost cap (forwarded to orchestrator when supported)
  --output-dir <path>        Output directory (sets SPECA_OUTPUT_DIR)
  --no-tui                   Force plain-text pass-through (M6)
  --json                     Emit raw NDJSON events on stdout (M6)
  --help, -h                 Show this help

Examples
  $ speca run --phase 01a
  $ speca run --target 03 --workers 4 --max-concurrent 8
  $ speca run --phase 01b --force
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
}

function parsePhaseList(raw: unknown): string[] | undefined {
  if (raw === undefined) return undefined;
  if (typeof raw === "string") return raw.split(",").map((s) => s.trim()).filter(Boolean);
  if (Array.isArray(raw)) return raw.map(String).filter(Boolean);
  return undefined;
}

/**
 * Headless / pass-through mode. Used for `--no-tui`, `--json`, and when
 * stdout is not a TTY. We forward stderr to our stderr and (for `--json`)
 * stdout NDJSON lines verbatim. The TUI dashboard is bypassed.
 */
async function runHeadless(opts: RunOptions, spawnOpts: SpawnPipelineOptions): Promise<number> {
  const spawnFn = opts.spawn ?? spawnPipeline;
  const handle = spawnFn(spawnOpts);
  handle.on("event", (event) => {
    // In `--json` mode we re-emit the parsed event as one JSON line on
    // stdout. In `--no-tui` mode we render a friendly one-line summary.
    if (opts.flags.json) {
      process.stdout.write(JSON.stringify(event) + "\n");
    } else {
      const summary = formatEventSummary(event);
      if (summary) process.stdout.write(summary + "\n");
    }
  });
  handle.on("warn", (failure) => {
    process.stderr.write(`[speca run] warn: ${failure.reason}\n`);
  });
  handle.on("stderr", (line) => {
    process.stderr.write(line + "\n");
  });
  handle.on("spawn-error", (err) => {
    process.stderr.write(`[speca run] failed to spawn orchestrator: ${err.message}\n`);
  });
  return handle.done;
}

function formatEventSummary(event: { type: string } & Record<string, unknown>): string | null {
  switch (event.type) {
    case "pipeline-started":
      return `[pipeline] started: phases=${JSON.stringify(event.phases)}`;
    case "pipeline-completed":
      return `[pipeline] completed in ${(event.duration_s as number)?.toFixed?.(2)}s`;
    case "phase-started":
      return `[${event.phase}] started (workers=${event.workers}, max-concurrent=${event.max_concurrent})`;
    case "phase-completed":
      return `[${event.phase}] done (${event.total_results} results, ${(event.duration_s as number)?.toFixed?.(2)}s)`;
    case "phase-failed":
      return `[${event.phase}] FAILED: ${event.reason}`;
    case "budget-exceeded":
      return `[${event.phase}] BUDGET EXCEEDED: $${event.cost_usd} / $${event.max_budget_usd}`;
    case "circuit-breaker-tripped":
      return `[${event.phase}] CIRCUIT BREAKER TRIPPED: ${event.reason}`;
    default:
      return null;
  }
}

export async function runRunCommand(opts: RunOptions): Promise<number> {
  const phases = parsePhaseList(opts.flags.phase as unknown);
  if (!phases?.length && !opts.flags.target) {
    process.stderr.write("speca run: must pass --phase <id...> or --target <id>\n");
    process.stderr.write(HELP_TEXT);
    return 2;
  }

  const cwd = opts.cwd ?? process.cwd();
  const outputDir = opts.flags.outputDir ? resolve(cwd, opts.flags.outputDir) : undefined;
  const spawnOpts: SpawnPipelineOptions = {
    phases,
    target: opts.flags.target,
    workers: opts.flags.workers,
    maxConcurrent: opts.flags.maxConcurrent,
    force: opts.flags.force,
    outputDir,
    cwd,
    budget: opts.flags.budget,
  };

  const headless = opts.flags.noTui || opts.flags.json || process.stdout.isTTY !== true;
  if (headless) {
    return runHeadless(opts, spawnOpts);
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
    process.stderr.write(`[speca run] failed to spawn orchestrator: ${err.message}\n`);
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

  const app = render(createElement(Dashboard, { store, handle, cwd }));
  const exitCode = await handle.done;
  await app.waitUntilExit();
  await stopLogs?.();
  return exitCode;
}
