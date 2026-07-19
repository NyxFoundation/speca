/**
 * `speca attach` — read-only attach to a running pipeline in cwd (issue #27).
 *
 * Unlike `speca run`, no orchestrator subprocess is spawned and no signal is
 * ever sent to one. Everything is derived from the artifacts the orchestrator
 * writes to disk:
 *
 *   1. `outputs/{phase}_PARTIAL_*.json` — seeds the phase rows
 *      (lib/pipeline/attach.ts).
 *   2. `outputs/logs/*.log.jsonl` — the existing `startLogWatcher` tails
 *      these; because its cursors start at byte 0, the backlog already on
 *      disk is replayed into the log pane before new lines stream in.
 *
 * Modes:
 *   - TTY: the same Ink dashboard as `speca run`, in read-only mode (no
 *     stop / force keybindings; `q` only detaches, never signals the run).
 *   - `--no-tui` / `--json` / non-TTY: headless tail — a scan summary
 *     followed by one line per log event, until SIGINT (or the test-seam
 *     AbortSignal) detaches.
 *
 * When no pipeline artifacts are found at all, prints a hint and exits 0
 * (per the issue's acceptance: detecting "nothing to attach to" is a normal
 * outcome, not an error).
 */
import { render } from "ink";
import { createElement } from "react";

import { Dashboard } from "../components/Dashboard.js";
import { emitJson, getOutputMode, printNoTui } from "../lib/io/output-mode.js";
import {
  buildAttachSnapshot,
  scanAttachState,
  type AttachScan,
} from "../lib/pipeline/attach.js";
import { startLogWatcher, type LogLine } from "../lib/pipeline/log-watcher.js";
import { PipelineStore } from "../lib/pipeline/store.js";
import { ThemeProvider } from "../lib/theme/index.js";

export interface AttachCommandFlags {
  outputDir?: string;
  noTui?: boolean;
  json?: boolean;
}

const HELP_TEXT = `\
speca attach — read-only attach to a running pipeline in cwd

Usage
  $ speca attach

Reads outputs/*_PARTIAL_*.json and outputs/logs/*.log.jsonl written by a
'speca run' (in this or another terminal) and renders the same dashboard,
without spawning a new orchestrator. Detaching (q) never stops the run.

Flags
  --output-dir <path>        Attach to a run using a non-default output dir
  --no-tui                   Plain-text tail (scan summary + log lines)
  --json                     NDJSON tail (attach-summary + log records)
  --help, -h                 Show this help

Exit codes
  0   Detached normally, or no pipeline artifacts found (a hint is printed)

Examples
  $ speca attach
  $ speca attach --output-dir ./outputs
  $ speca attach --json | jq .summary
`;

export function printAttachHelp(): void {
  process.stdout.write(HELP_TEXT);
}

export interface AttachOptions {
  flags: AttachCommandFlags;
  cwd?: string;
  /** Test seam — defaults to the chokidar-polling log watcher. */
  startLogs?: typeof startLogWatcher;
  /** Test seam — abort the headless tail loop (defaults to SIGINT). */
  signal?: AbortSignal;
  /** Test seam — "now" for the active-phase window (defaults to Date.now()). */
  nowMs?: number;
}

function formatLogLine(line: LogLine): string {
  const where = line.phase !== "" ? `[${line.phase}/W${line.worker}/B${line.batch}] ` : "";
  return `${where}${line.summary}`;
}

function describeScan(scan: AttachScan, nowMs: number): string {
  const phases = scan.phases
    .map((p) => `${p.id}(${p.partialBatches} partial${p.partialBatches === 1 ? "" : "s"})`)
    .join(", ");
  const ageS = scan.latestActivityMs > 0 ? Math.max(0, Math.round((nowMs - scan.latestActivityMs) / 1000)) : null;
  return `speca attach: ${scan.phases.length} phase(s) on disk [${phases}]${ageS != null ? `, last activity ${ageS}s ago` : ""}`;
}

const NO_RUN_HINT = `\
speca attach: no pipeline artifacts found — nothing to attach to.
Hint: run 'speca run --phase <id...>' in this directory first (or pass
--output-dir if the run writes somewhere other than ./outputs).
`;

/**
 * Headless tail: print the scan summary, then stream log lines until the
 * abort signal fires (Ctrl-C detaches; the run itself is untouched).
 */
async function runHeadless(
  opts: AttachOptions,
  scan: AttachScan,
  mode: "json" | "no-tui",
): Promise<number> {
  const nowMs = opts.nowMs ?? Date.now();
  if (mode === "json") {
    emitJson({
      type: "attach-summary",
      outputsDir: scan.outputsDir,
      phases: scan.phases.map((p) => ({
        id: p.id,
        partial_batches: p.partialBatches,
        items: p.items,
        workers: p.workers,
        last_activity: p.lastActivityMs > 0 ? new Date(p.lastActivityMs).toISOString() : null,
      })),
    });
  } else {
    printNoTui(describeScan(scan, nowMs));
  }

  const startLogs = opts.startLogs ?? startLogWatcher;
  let stopLogs: (() => Promise<void>) | null = null;
  try {
    stopLogs = await startLogs({
      dir: scan.logsDir,
      onLine: (line) => {
        if (mode === "json") {
          // `LogLine.type` is the Claude stream-json type — keep it under
          // `event_type` so the NDJSON envelope discriminator stays "log".
          const { type: eventType, ...rest } = line;
          emitJson({ ...rest, type: "log", event_type: eventType });
        } else {
          printNoTui(formatLogLine(line));
        }
      },
      onWarn: (msg) => process.stderr.write(`[speca attach] log-watcher: ${msg}\n`),
    });
  } catch (err) {
    process.stderr.write(`[speca attach] log-watcher unavailable: ${(err as Error).message}\n`);
    return 1;
  }

  // Tail until detached. SIGINT is the documented detach path; tests pass
  // an AbortSignal instead so the loop is deterministic.
  await new Promise<void>((resolvePromise) => {
    if (opts.signal) {
      if (opts.signal.aborted) return resolvePromise();
      opts.signal.addEventListener("abort", () => resolvePromise(), { once: true });
      return;
    }
    const onSigint = (): void => {
      process.off("SIGINT", onSigint);
      resolvePromise();
    };
    process.on("SIGINT", onSigint);
  });
  await stopLogs?.();
  return 0;
}

export async function runAttachCommand(opts: AttachOptions): Promise<number> {
  const cwd = opts.cwd ?? process.cwd();
  const nowMs = opts.nowMs ?? Date.now();
  const scan = await scanAttachState({ cwd, outputDir: opts.flags.outputDir });

  if (!scan.detected) {
    // Acceptance (#27): exit 0 with a hint, never a crash.
    process.stdout.write(NO_RUN_HINT);
    return 0;
  }

  const outputMode = getOutputMode({ noTui: opts.flags.noTui, json: opts.flags.json });
  if (outputMode !== "tui") {
    return runHeadless(opts, scan, outputMode);
  }

  // TUI mode: seed the store from disk, then let the log watcher stream.
  const store = new PipelineStore();
  store.seedSnapshot(buildAttachSnapshot(scan, nowMs));

  const startLogs = opts.startLogs ?? startLogWatcher;
  let stopLogs: (() => Promise<void>) | null = null;
  try {
    stopLogs = await startLogs({
      dir: scan.logsDir,
      onLine: (line) => store.applyLog(line),
      onWarn: (msg) => process.stderr.write(`[speca attach] log-watcher: ${msg}\n`),
    });
  } catch (err) {
    process.stderr.write(`[speca attach] log-watcher unavailable: ${(err as Error).message}\n`);
  }

  // No `handle` — the dashboard has nothing to signal in read-only mode.
  const app = render(
    createElement(
      ThemeProvider,
      null,
      createElement(Dashboard, { store, cwd, readOnly: true, title: "speca attach" }),
    ),
  );
  await app.waitUntilExit();
  await stopLogs?.();
  return 0;
}
