/**
 * Pipeline run store.
 *
 * A plain TypeScript event-driven store: NDJSON events from the orchestrator
 * subprocess and `log-watcher` log lines are folded into a single immutable
 * snapshot. React subscribes via `useSyncExternalStore` (see useStore.ts).
 *
 * We deliberately avoid React state for the dashboard so we can decouple the
 * subscription from rendering and so we can unit-test reducers without Ink.
 */
import type { LogLine } from "./log-watcher.js";
import type { PipelineEvent } from "./events.js";

export type PhaseStatus = "pending" | "running" | "done" | "failed";

export interface PhaseState {
  id: string;
  status: PhaseStatus;
  startedAt?: string;
  endedAt?: string;
  durationS?: number;
  totalResults?: number;
  failureReason?: string;
  workers?: number;
  maxConcurrent?: number;
  model?: string | null;
  // Worker activity (worker id → most recent log line summary).
  workerActivity: Record<string, string>;
  // Counters for progress display.
  batchesObserved: number;
}

export interface CostState {
  total_usd: number;
  max_budget_usd: number | null;
}

export type PipelineStatus =
  | "idle"
  | "running"
  | "completed"
  | "failed"
  | "budget-exceeded"
  | "circuit-broken";

export interface PipelineSnapshot {
  pipelineStatus: PipelineStatus;
  phases: Map<string, PhaseState>;
  /** Order phases were registered in (`pipeline-started.phases` order). */
  phaseOrder: string[];
  workers: Map<string, { id: string; phase?: string; lastSummary?: string }>;
  logs: LogLine[];
  cost: CostState;
  startedAt?: string;
  endedAt?: string;
  /** Last failure / abort reason, surfaced in the status bar. */
  lastError?: string;
}

export const LOG_RING_CAPACITY = 500;

export function createInitialSnapshot(): PipelineSnapshot {
  return {
    pipelineStatus: "idle",
    phases: new Map(),
    phaseOrder: [],
    workers: new Map(),
    logs: [],
    cost: { total_usd: 0, max_budget_usd: null },
  };
}

function ensurePhase(snap: PipelineSnapshot, id: string): PhaseState {
  let phase = snap.phases.get(id);
  if (!phase) {
    phase = {
      id,
      status: "pending",
      workerActivity: {},
      batchesObserved: 0,
    };
    snap.phases.set(id, phase);
    if (!snap.phaseOrder.includes(id)) snap.phaseOrder.push(id);
  }
  return phase;
}

function cloneSnapshot(snap: PipelineSnapshot): PipelineSnapshot {
  return {
    pipelineStatus: snap.pipelineStatus,
    phases: new Map([...snap.phases].map(([k, v]) => [k, { ...v, workerActivity: { ...v.workerActivity } }])),
    phaseOrder: [...snap.phaseOrder],
    workers: new Map([...snap.workers].map(([k, v]) => [k, { ...v }])),
    logs: snap.logs,
    cost: { ...snap.cost },
    startedAt: snap.startedAt,
    endedAt: snap.endedAt,
    lastError: snap.lastError,
  };
}

/**
 * Apply a single PipelineEvent. Pure reducer — returns a new snapshot.
 */
export function applyPipelineEvent(prev: PipelineSnapshot, event: PipelineEvent): PipelineSnapshot {
  const snap = cloneSnapshot(prev);
  switch (event.type) {
    case "pipeline-started": {
      snap.pipelineStatus = "running";
      snap.startedAt = event.ts;
      snap.endedAt = undefined;
      snap.lastError = undefined;
      for (const id of event.phases) {
        ensurePhase(snap, id);
      }
      return snap;
    }
    case "phase-started": {
      const phase = ensurePhase(snap, event.phase);
      phase.status = "running";
      phase.startedAt = event.ts;
      phase.workers = event.workers;
      phase.maxConcurrent = event.max_concurrent;
      phase.model = event.model ?? null;
      phase.failureReason = undefined;
      return snap;
    }
    case "phase-completed": {
      const phase = ensurePhase(snap, event.phase);
      phase.status = "done";
      phase.endedAt = event.ts;
      phase.durationS = event.duration_s;
      phase.totalResults = event.total_results;
      return snap;
    }
    case "phase-failed": {
      const phase = ensurePhase(snap, event.phase);
      // Don't downgrade a phase that we already marked done.
      if (phase.status !== "done") {
        phase.status = "failed";
      }
      phase.endedAt = event.ts;
      phase.durationS = event.duration_s;
      phase.failureReason = event.reason;
      snap.lastError = `Phase ${event.phase} failed: ${event.reason}`;
      return snap;
    }
    case "budget-exceeded": {
      snap.pipelineStatus = "budget-exceeded";
      if (event.cost_usd != null) snap.cost.total_usd = event.cost_usd;
      if (event.max_budget_usd != null) snap.cost.max_budget_usd = event.max_budget_usd;
      snap.lastError = `Budget exceeded on ${event.phase}: $${(event.cost_usd ?? 0).toFixed(2)} / $${(event.max_budget_usd ?? 0).toFixed(2)}`;
      return snap;
    }
    case "circuit-breaker-tripped": {
      snap.pipelineStatus = "circuit-broken";
      snap.lastError = `Circuit breaker tripped on ${event.phase}: ${event.reason}`;
      return snap;
    }
    case "pipeline-completed": {
      snap.endedAt = event.ts;
      // Status: completed if every phase succeeded, otherwise failed.
      const allOk = Object.values(event.results).every(Boolean);
      // Don't override budget-exceeded / circuit-broken which are more specific.
      if (snap.pipelineStatus === "running") {
        snap.pipelineStatus = allOk ? "completed" : "failed";
      }
      return snap;
    }
  }
}

/**
 * Apply a single LogLine (from the file-tail watcher). Side-effect: appends
 * to the ring buffer (capped at LOG_RING_CAPACITY) and updates per-phase
 * worker activity for the dashboard.
 */
export function applyLogLine(prev: PipelineSnapshot, line: LogLine): PipelineSnapshot {
  const snap = cloneSnapshot(prev);
  // Ring buffer.
  const next = snap.logs.length >= LOG_RING_CAPACITY ? snap.logs.slice(-LOG_RING_CAPACITY + 1) : snap.logs.slice();
  next.push(line);
  snap.logs = next;

  if (line.phase !== "") {
    const phase = ensurePhase(snap, line.phase);
    if (line.worker !== "") {
      phase.workerActivity[`W${line.worker}`] = line.summary;
    }
    phase.batchesObserved += 1;
    // Workers collection (across all phases).
    if (line.worker !== "") {
      const wid = `W${line.worker}`;
      snap.workers.set(wid, { id: wid, phase: line.phase, lastSummary: line.summary });
    }
  }
  return snap;
}

/**
 * In-process subscribable store. Compatible with React's
 * `useSyncExternalStore`.
 */
export class PipelineStore {
  private snap: PipelineSnapshot = createInitialSnapshot();
  private listeners: Set<() => void> = new Set();

  getSnapshot = (): PipelineSnapshot => this.snap;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  applyEvent(event: PipelineEvent): void {
    this.snap = applyPipelineEvent(this.snap, event);
    this.notify();
  }

  applyLog(line: LogLine): void {
    this.snap = applyLogLine(this.snap, line);
    this.notify();
  }

  setBudget(maxUsd: number): void {
    this.snap = { ...this.snap, cost: { ...this.snap.cost, max_budget_usd: maxUsd } };
    this.notify();
  }

  /** Replace the snapshot (for tests). */
  reset(): void {
    this.snap = createInitialSnapshot();
    this.notify();
  }

  private notify(): void {
    for (const l of this.listeners) l();
  }
}
