/**
 * attach.ts — reconstruct a dashboard snapshot from on-disk pipeline
 * artifacts, without talking to (or spawning) the orchestrator.
 *
 * `speca attach` (issue #27) is read-only: it never receives the NDJSON
 * event stream `speca run` gets on the orchestrator's stdout. Everything it
 * knows comes from two on-disk surfaces the orchestrator already maintains:
 *
 *   - `outputs/{phase}_PARTIAL_W{worker}B{batch}_{ts}.json` — one file per
 *     completed batch (see scripts/orchestrator/collector.py).
 *   - `outputs/logs/{phase}_w{worker}b{batch}_{ts}.log.jsonl` — the Claude
 *     stream-json tail per batch (see scripts/orchestrator/runner.py).
 *
 * From filenames + mtimes alone we can reconstruct which phases have run,
 * which workers were active, and roughly whether a phase is still moving
 * (recent writes) or has gone quiet. We deliberately do NOT guess metrics
 * the event stream would have carried (duration_s, total_results, cost):
 * those fields stay unset rather than being fabricated.
 */
import { promises as fs } from "node:fs";
import { join, resolve } from "node:path";

import { parseLogFilename } from "./log-watcher.js";
import {
  createInitialSnapshot,
  type PipelineSnapshot,
  type PhaseState,
} from "./store.js";

/** A phase is considered "still running" if any of its artifacts were
 * written within this window. Beyond it we render the phase as done —
 * the orchestrator writes PARTIALs continuously while a phase runs, so a
 * quiet phase is either finished or aborted; either way it is not "live". */
export const ATTACH_ACTIVE_WINDOW_MS = 5 * 60 * 1000;

/** Parsed `{phase}_PARTIAL_W{worker}B{batch}_{ts}.json` filename. */
export interface PartialFileMeta {
  phase: string;
  worker: string;
  batch: string;
  /** Unix-seconds timestamp suffix, or "" for legacy names without one. */
  ts: string;
}

/**
 * Filename → meta parser for PARTIAL outputs. Returns null when the name
 * does not follow the collector's convention (STATE / CONTEXT / QUEUE /
 * ASYNC_QUEUE files all return null on purpose).
 */
export function parsePartialFilename(filename: string): PartialFileMeta | null {
  const m = filename.match(/^([0-9a-zA-Z]+)_PARTIAL_W(\d+)B(\d+)(?:_(\d+))?\.json$/);
  if (!m) return null;
  return { phase: m[1] ?? "", worker: m[2] ?? "", batch: m[3] ?? "", ts: m[4] ?? "" };
}

export interface AttachPhaseSeed {
  id: string;
  /** Distinct worker ids observed for this phase (from PARTIAL + log names). */
  workers: string[];
  /** Number of PARTIAL batch files observed on disk. */
  partialBatches: number;
  /** Result items counted from PARTIAL payloads (`metadata.item_count`,
   * falling back to `audit_items` / `reviewed_items` length). */
  items: number;
  /** Epoch ms of the newest artifact belonging to this phase. */
  lastActivityMs: number;
  /** Epoch ms of the oldest artifact belonging to this phase. */
  firstActivityMs: number;
}

export interface AttachScan {
  /** True when at least one PARTIAL or log file was found. */
  detected: boolean;
  /** Per-phase seeds, sorted by phase id (lexicographic = pipeline order
   * for the canonical 01a…04 set). */
  phases: AttachPhaseSeed[];
  /** Epoch ms of the newest artifact across all phases (0 when none). */
  latestActivityMs: number;
  outputsDir: string;
  logsDir: string;
}

export interface ScanOptions {
  /** Project directory (defaults to process.cwd()). */
  cwd?: string;
  /** Explicit outputs dir (equivalent of `--output-dir`); overrides cwd/outputs. */
  outputDir?: string;
}

async function statMtime(path: string): Promise<number> {
  try {
    const st = await fs.stat(path);
    return st.mtimeMs;
  } catch {
    return 0;
  }
}

async function listDir(dir: string): Promise<string[]> {
  try {
    return await fs.readdir(dir);
  } catch {
    return [];
  }
}

/**
 * Scan `outputs/` (+ `outputs/logs/`) and build per-phase seeds from the
 * artifact filenames + mtimes. Missing directories yield an empty scan
 * (`detected: false`) — never an exception.
 */
export async function scanAttachState(options: ScanOptions = {}): Promise<AttachScan> {
  const cwd = options.cwd ?? process.cwd();
  const outputsDir = options.outputDir ? resolve(cwd, options.outputDir) : resolve(cwd, "outputs");
  const logsDir = join(outputsDir, "logs");

  interface Acc {
    workers: Set<string>;
    partialBatches: number;
    items: number;
    lastActivityMs: number;
    firstActivityMs: number;
  }
  const byPhase = new Map<string, Acc>();
  const ensure = (phase: string): Acc => {
    let acc = byPhase.get(phase);
    if (!acc) {
      acc = { workers: new Set(), partialBatches: 0, items: 0, lastActivityMs: 0, firstActivityMs: Number.POSITIVE_INFINITY };
      byPhase.set(phase, acc);
    }
    return acc;
  };
  const touch = (acc: Acc, mtimeMs: number): void => {
    if (mtimeMs <= 0) return;
    if (mtimeMs > acc.lastActivityMs) acc.lastActivityMs = mtimeMs;
    if (mtimeMs < acc.firstActivityMs) acc.firstActivityMs = mtimeMs;
  };

  for (const name of await listDir(outputsDir)) {
    const meta = parsePartialFilename(name);
    if (!meta) continue;
    const acc = ensure(meta.phase);
    acc.partialBatches += 1;
    acc.workers.add(meta.worker);
    const path = join(outputsDir, name);
    acc.items += await countPartialItems(path);
    touch(acc, await statMtime(path));
  }
  for (const name of await listDir(logsDir)) {
    const meta = parseLogFilename(name);
    if (!meta) continue;
    const acc = ensure(meta.phase);
    acc.workers.add(meta.worker);
    touch(acc, await statMtime(join(logsDir, name)));
  }

  const phases: AttachPhaseSeed[] = [...byPhase.entries()]
    .map(([id, acc]) => ({
      id,
      workers: [...acc.workers].sort((a, b) => Number(a) - Number(b)),
      partialBatches: acc.partialBatches,
      items: acc.items,
      lastActivityMs: acc.lastActivityMs,
      firstActivityMs: Number.isFinite(acc.firstActivityMs) ? acc.firstActivityMs : 0,
    }))
    .sort((a, b) => a.id.localeCompare(b.id));

  const latestActivityMs = phases.reduce((max, p) => Math.max(max, p.lastActivityMs), 0);
  return { detected: phases.length > 0, phases, latestActivityMs, outputsDir, logsDir };
}

/**
 * Count result items in a single PARTIAL file. Prefers the collector's
 * `metadata.item_count`, falling back to the payload array lengths. Lenient:
 * any read/parse failure counts as 0 (partial files can be mid-write while
 * we attach — the log watcher has the same tolerance).
 */
async function countPartialItems(path: string): Promise<number> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(await fs.readFile(path, "utf8"));
  } catch {
    return 0;
  }
  if (typeof parsed !== "object" || parsed === null) return 0;
  const obj = parsed as {
    metadata?: { item_count?: unknown };
    audit_items?: unknown;
    reviewed_items?: unknown;
  };
  const declared = obj.metadata?.item_count;
  if (typeof declared === "number" && Number.isFinite(declared) && declared >= 0) return declared;
  if (Array.isArray(obj.audit_items)) return obj.audit_items.length;
  if (Array.isArray(obj.reviewed_items)) return obj.reviewed_items.length;
  return 0;
}

/**
 * Decide the dashboard status for a seeded phase: "running" when its newest
 * artifact is within the active window, "done" otherwise. We never seed
 * "failed" — failure is only knowable from the event stream we don't have.
 */
export function seedPhaseStatus(
  seed: AttachPhaseSeed,
  nowMs: number,
  activeWindowMs: number = ATTACH_ACTIVE_WINDOW_MS,
): "running" | "done" {
  return nowMs - seed.lastActivityMs <= activeWindowMs ? "running" : "done";
}

/**
 * Build the initial {@link PipelineSnapshot} for the attach dashboard.
 *
 * - Phase order = sorted phase ids (matches pipeline order for the
 *   canonical set).
 * - Status via {@link seedPhaseStatus}; a live run keeps updating through
 *   the log watcher after this snapshot is seeded.
 * - `totalResults` comes from real PARTIAL item counts — never invented.
 * - `pipelineStatus` is "running" when any phase is active, else "idle"
 *   (NOT "completed": without the event stream we cannot distinguish
 *   success from an aborted run, and "idle" makes no claim).
 */
export function buildAttachSnapshot(
  scan: AttachScan,
  nowMs: number = Date.now(),
  activeWindowMs: number = ATTACH_ACTIVE_WINDOW_MS,
): PipelineSnapshot {
  const snap = createInitialSnapshot();
  let anyRunning = false;
  let earliest = Number.POSITIVE_INFINITY;
  for (const seed of scan.phases) {
    const status = seedPhaseStatus(seed, nowMs, activeWindowMs);
    if (status === "running") anyRunning = true;
    if (seed.firstActivityMs > 0 && seed.firstActivityMs < earliest) earliest = seed.firstActivityMs;
    const workerActivity: Record<string, string> = {};
    for (const w of seed.workers) workerActivity[`W${w}`] = "(observed on disk)";
    const phase: PhaseState = {
      id: seed.id,
      status,
      workerActivity,
      batchesObserved: seed.partialBatches,
      workers: seed.workers.length > 0 ? seed.workers.length : undefined,
      totalResults: seed.items > 0 ? seed.items : undefined,
      startedAt: seed.firstActivityMs > 0 ? new Date(seed.firstActivityMs).toISOString() : undefined,
      endedAt: status === "done" && seed.lastActivityMs > 0 ? new Date(seed.lastActivityMs).toISOString() : undefined,
    };
    snap.phases.set(seed.id, phase);
    snap.phaseOrder.push(seed.id);
    for (const w of seed.workers) {
      snap.workers.set(`W${w}`, { id: `W${w}`, phase: seed.id, lastSummary: "(observed on disk)" });
    }
  }
  snap.pipelineStatus = anyRunning ? "running" : "idle";
  if (Number.isFinite(earliest)) snap.startedAt = new Date(earliest).toISOString();
  return snap;
}
