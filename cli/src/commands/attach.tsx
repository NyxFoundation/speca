/**
 * `speca attach` — read-only attach to a running pipeline in cwd (issue #27).
 *
 * Unlike `speca run`, no orchestrator subprocess is spawned, no signal is
 * ever sent to one, and nothing is created or modified on disk — not even
 * `outputs/logs/` (the log watcher is started with `mkdirMissing: false`,
 * and only once the directory actually exists; see #118 follow-ups).
 * Everything is derived from the artifacts the orchestrator writes:
 *
 *   1. `outputs/{phase}_PARTIAL_*.json` — seeds the phase rows
 *      (lib/pipeline/attach.ts).
 *   2. `outputs/logs/*.log.jsonl` — the existing `startLogWatcher` tails
 *      these; because its cursors start at byte 0, the backlog already on
 *      disk is replayed into the log pane before new lines stream in.
 *
 * A periodic disk re-scan (every ATTACH_RESCAN_INTERVAL_MS) keeps the
 * dashboard truthful over a long-lived attach: phase statuses flip
 * running → done as artifacts go quiet, new batches/phases appear, and the
 * log watcher is started late if `outputs/logs/` shows up after attach.
 *
 * Modes:
 *   - TTY: the same Ink dashboard as `speca run`, in read-only mode (no
 *     stop / force keybindings; `q`, Ctrl-C, and SIGTERM all just detach —
 *     the run itself is never touched).
 *   - `--no-tui` / `--json` / non-TTY: headless tail — a scan summary
 *     followed by one line per log event, until SIGINT / SIGTERM (or the
 *     test-seam AbortSignal) detaches.
 *
 * When no pipeline artifacts are found at all, prints a hint and exits 0
 * (per the issue's acceptance: detecting "nothing to attach to" is a normal
 * outcome, not an error).
 */
import { promises as fs } from "node:fs";
import { render } from "ink";
import { createElement } from "react";

import { Dashboard } from "../components/Dashboard.js";
import { emitJson, getOutputMode, printNoTui } from "../lib/io/output-mode.js";
import {
  ATTACH_RESCAN_INTERVAL_MS,
  buildAttachSnapshot,
  mergeAttachRescan,
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
without spawning a new orchestrator. Attach never creates or modifies
anything on disk, and detaching (q / Ctrl-C / SIGTERM) never stops the run.

Flags
  --output-dir <path>        Attach to a run using a non-default output dir
  --no-tui                   Plain-text tail (scan summary + log lines)
  --json                     NDJSON tail (attach-summary + log records)
  --help, -h                 Show this help

Exit codes
  0   Detached normally (q / Ctrl-C / SIGTERM), or no pipeline artifacts
      were found (a hint is printed)
  1   Initial log-watcher start failed in headless mode. Only the startup
      attempt exits 1 — later retry failures (e.g. logs dir appearing
      mid-session) warn on stderr and keep tailing. TUI mode degrades to
      phase rows only and still exits 0.

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
  /** Test seam — abort the headless tail loop (defaults to SIGINT/SIGTERM). */
  signal?: AbortSignal;
  /** Test seam — "now" for the active-phase window (defaults to Date.now()). */
  nowMs?: number;
  /** Test seam — disk re-scan cadence (defaults to ATTACH_RESCAN_INTERVAL_MS). */
  rescanIntervalMs?: number;
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

async function dirExists(dir: string): Promise<boolean> {
  try {
    return (await fs.stat(dir)).isDirectory();
  } catch {
    return false;
  }
}

/**
 * Read-only watcher lifecycle: start only when the logs directory already
 * exists (never mkdir — see log-watcher's `mkdirMissing`), and let the
 * rescan timer retry until it appears. chokidar cannot pick up a watch
 * target created after the watch is armed, so late-starting runs depend on
 * this retry.
 */
interface WatcherState {
  stop: (() => Promise<void>) | null;
  /** Set when a start attempt threw — we warn once and stop retrying. */
  failed: boolean;
  /**
   * Set on teardown (#121 follow-up). A rescan-timer start attempt can be
   * mid-`await` when detach fires; without this flag its late-arriving
   * watcher would be assigned after teardown already ran and leak. Any
   * start that completes after `stopped` disposes itself immediately.
   */
  stopped: boolean;
}

async function tryStartWatcher(
  state: WatcherState,
  logsDir: string,
  startLogs: typeof startLogWatcher,
  onLine: (line: LogLine) => void,
): Promise<void> {
  if (state.stop || state.failed || state.stopped) return;
  if (!(await dirExists(logsDir))) return;
  if (state.stopped) return;
  try {
    const stop = await startLogs({
      dir: logsDir,
      mkdirMissing: false,
      onLine,
      onWarn: (msg) => process.stderr.write(`[speca attach] log-watcher: ${msg}\n`),
    });
    if (state.stopped) {
      // Detached while the start was in flight — dispose, don't leak.
      await stop();
      return;
    }
    state.stop = stop;
  } catch (err) {
    state.failed = true;
    process.stderr.write(`[speca attach] log-watcher unavailable: ${(err as Error).message}\n`);
  }
}

/** Single teardown path for both modes: flag first, then dispose. */
async function stopWatcher(state: WatcherState): Promise<void> {
  state.stopped = true;
  const stop = state.stop;
  state.stop = null;
  await stop?.();
}

/** Resolve on detach: AbortSignal (tests) or SIGINT / SIGTERM. */
function waitForDetach(signal?: AbortSignal): Promise<void> {
  return new Promise<void>((resolvePromise) => {
    if (signal) {
      if (signal.aborted) return resolvePromise();
      signal.addEventListener("abort", () => resolvePromise(), { once: true });
      return;
    }
    const onSig = (): void => {
      process.off("SIGINT", onSig);
      process.off("SIGTERM", onSig);
      resolvePromise();
    };
    process.on("SIGINT", onSig);
    process.on("SIGTERM", onSig);
  });
}

/**
 * Headless tail: print the scan summary, then stream log lines until the
 * detach signal fires. Exit 1 only when a start attempt for an existing
 * logs directory threw (a missing directory just means "keep waiting").
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
  const watcher: WatcherState = { stop: null, failed: false, stopped: false };
  const onLine = (line: LogLine): void => {
    if (mode === "json") {
      // `LogLine.type` is the Claude stream-json type — keep it under
      // `event_type` so the NDJSON envelope discriminator stays "log".
      const { type: eventType, ...rest } = line;
      emitJson({ ...rest, type: "log", event_type: eventType });
    } else {
      printNoTui(formatLogLine(line));
    }
  };

  await tryStartWatcher(watcher, scan.logsDir, startLogs, onLine);
  if (watcher.failed) return 1;

  // The logs dir may not exist yet (attach raced ahead of the run's first
  // log write) — retry from a timer until it appears. Deliberately NOT
  // unref'd: signal listeners alone do not keep the Node event loop alive,
  // so before the watcher starts this timer is the only thing preventing
  // the headless tail from exiting on the spot.
  const rescanMs = opts.rescanIntervalMs ?? ATTACH_RESCAN_INTERVAL_MS;
  const timer = setInterval(() => {
    void tryStartWatcher(watcher, scan.logsDir, startLogs, onLine);
  }, rescanMs);

  await waitForDetach(opts.signal);
  clearInterval(timer);
  await stopWatcher(watcher);
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
  const watcher: WatcherState = { stop: null, failed: false, stopped: false };
  await tryStartWatcher(watcher, scan.logsDir, startLogs, (line) => store.applyLog(line));

  // Periodic re-scan (#118 follow-up): keep phase statuses / batch counts
  // truthful over a long-lived attach, and start the watcher late if
  // outputs/logs/ appears after we did. Ticks are serialised via a flag so
  // a slow disk can't stack scans.
  const rescanMs = opts.rescanIntervalMs ?? ATTACH_RESCAN_INTERVAL_MS;
  let rescanInFlight = false;
  const timer = setInterval(() => {
    if (rescanInFlight) return;
    rescanInFlight = true;
    void (async () => {
      try {
        const fresh = await scanAttachState({ cwd, outputDir: opts.flags.outputDir });
        store.seedSnapshot(
          mergeAttachRescan(store.getSnapshot(), buildAttachSnapshot(fresh, Date.now())),
        );
        await tryStartWatcher(watcher, fresh.logsDir, startLogs, (line) => store.applyLog(line));
      } catch {
        // A transient scan failure must never kill the dashboard.
      } finally {
        rescanInFlight = false;
      }
    })();
  }, rescanMs);
  timer.unref?.();

  // No `handle` — the dashboard has nothing to signal in read-only mode.
  const app = render(
    createElement(
      ThemeProvider,
      null,
      createElement(Dashboard, { store, cwd, readOnly: true, title: "speca attach" }),
    ),
  );
  // SIGTERM detaches through the same cleanup path as `q` (#118 follow-up):
  // unmounting resolves waitUntilExit, after which the timer and watcher
  // are torn down below.
  const onSigterm = (): void => app.unmount();
  process.once("SIGTERM", onSigterm);
  try {
    await app.waitUntilExit();
  } finally {
    process.removeListener("SIGTERM", onSigterm);
    clearInterval(timer);
    await stopWatcher(watcher);
  }
  return 0;
}
