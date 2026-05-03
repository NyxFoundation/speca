import { describe, expect, it } from "vitest";
import {
  applyLogLine,
  applyPipelineEvent,
  createInitialSnapshot,
  PipelineStore,
  LOG_RING_CAPACITY,
} from "../src/lib/pipeline/store.js";
import type { LogLine } from "../src/lib/pipeline/log-watcher.js";
import type { PipelineEvent } from "../src/lib/pipeline/events.js";

const ts = "2026-05-03T12:00:00.000+00:00";

const ev = {
  pipelineStarted(phases: string[]): PipelineEvent {
    return { type: "pipeline-started", ts, phases, workers: 4, max_concurrent: 8, force: false };
  },
  phaseStarted(phase: string): PipelineEvent {
    return { type: "phase-started", ts, phase, workers: 4, max_concurrent: 8, force: false, model: "sonnet" };
  },
  phaseCompleted(phase: string, total = 5): PipelineEvent {
    return { type: "phase-completed", ts, phase, duration_s: 1.2, total_results: total };
  },
  phaseFailed(phase: string, reason = "boom"): PipelineEvent {
    return { type: "phase-failed", ts, phase, reason, duration_s: 0.5 };
  },
  pipelineCompleted(phases: string[], results: Record<string, boolean>): PipelineEvent {
    return { type: "pipeline-completed", ts, phases, results, duration_s: 3 };
  },
  budgetExceeded(phase: string): PipelineEvent {
    return { type: "budget-exceeded", ts, phase, cost_usd: 9.9, max_budget_usd: 10, duration_s: 600 };
  },
  circuit(phase: string): PipelineEvent {
    return { type: "circuit-breaker-tripped", ts, phase, reason: "fail-loop", stats: {}, duration_s: 60 };
  },
};

describe("applyPipelineEvent — happy-path transitions", () => {
  it("pipeline-started → phase-started → phase-completed → pipeline-completed", () => {
    let s = createInitialSnapshot();
    s = applyPipelineEvent(s, ev.pipelineStarted(["01a", "01b"]));
    expect(s.pipelineStatus).toBe("running");
    expect(s.phaseOrder).toEqual(["01a", "01b"]);
    expect(s.phases.get("01a")?.status).toBe("pending");

    s = applyPipelineEvent(s, ev.phaseStarted("01a"));
    expect(s.phases.get("01a")?.status).toBe("running");

    s = applyPipelineEvent(s, ev.phaseCompleted("01a", 28));
    expect(s.phases.get("01a")?.status).toBe("done");
    expect(s.phases.get("01a")?.totalResults).toBe(28);

    s = applyPipelineEvent(s, ev.phaseStarted("01b"));
    s = applyPipelineEvent(s, ev.phaseCompleted("01b", 41));
    s = applyPipelineEvent(s, ev.pipelineCompleted(["01a", "01b"], { "01a": true, "01b": true }));
    expect(s.pipelineStatus).toBe("completed");
    expect(s.endedAt).toBe(ts);
  });

  it("marks pipeline as failed when any phase failed", () => {
    let s = createInitialSnapshot();
    s = applyPipelineEvent(s, ev.pipelineStarted(["01a"]));
    s = applyPipelineEvent(s, ev.phaseStarted("01a"));
    s = applyPipelineEvent(s, ev.phaseFailed("01a", "dependency"));
    s = applyPipelineEvent(s, ev.pipelineCompleted(["01a"], { "01a": false }));
    expect(s.pipelineStatus).toBe("failed");
    expect(s.phases.get("01a")?.status).toBe("failed");
    expect(s.phases.get("01a")?.failureReason).toBe("dependency");
    expect(s.lastError).toContain("Phase 01a failed");
  });
});

describe("applyPipelineEvent — error / budget paths", () => {
  it("budget-exceeded sets pipelineStatus and cost", () => {
    let s = createInitialSnapshot();
    s = applyPipelineEvent(s, ev.pipelineStarted(["03"]));
    s = applyPipelineEvent(s, ev.budgetExceeded("03"));
    expect(s.pipelineStatus).toBe("budget-exceeded");
    expect(s.cost.total_usd).toBe(9.9);
    expect(s.cost.max_budget_usd).toBe(10);
    expect(s.lastError).toMatch(/Budget exceeded on 03/);
  });

  it("circuit-breaker-tripped sets pipelineStatus and lastError", () => {
    let s = createInitialSnapshot();
    s = applyPipelineEvent(s, ev.pipelineStarted(["03"]));
    s = applyPipelineEvent(s, ev.circuit("03"));
    expect(s.pipelineStatus).toBe("circuit-broken");
    expect(s.lastError).toMatch(/Circuit breaker tripped on 03/);
  });

  it("pipeline-completed does not downgrade an already-budget-exceeded status", () => {
    let s = createInitialSnapshot();
    s = applyPipelineEvent(s, ev.pipelineStarted(["03"]));
    s = applyPipelineEvent(s, ev.budgetExceeded("03"));
    s = applyPipelineEvent(s, ev.pipelineCompleted(["03"], { "03": false }));
    expect(s.pipelineStatus).toBe("budget-exceeded");
  });
});

describe("applyLogLine — ring buffer and worker activity", () => {
  function line(overrides: Partial<LogLine> = {}): LogLine {
    return {
      phase: "01a",
      worker: "0",
      batch: "1",
      ts,
      type: "assistant",
      summary: "tool_use: Grep",
      severity: "info",
      tool: "Grep",
      sourcePath: "/tmp/log.jsonl",
      ...overrides,
    };
  }

  it("appends to the log ring buffer and increments batchesObserved", () => {
    let s = createInitialSnapshot();
    s = applyLogLine(s, line());
    s = applyLogLine(s, line({ summary: "result: ok cost=$0.01", tool: null, type: "result" }));
    expect(s.logs).toHaveLength(2);
    const phase = s.phases.get("01a");
    expect(phase?.batchesObserved).toBe(2);
    expect(phase?.workerActivity).toEqual({ W0: "result: ok cost=$0.01" });
    expect(s.workers.get("W0")?.lastSummary).toMatch(/result/);
  });

  it("caps the ring buffer at LOG_RING_CAPACITY", () => {
    let s = createInitialSnapshot();
    for (let i = 0; i < LOG_RING_CAPACITY + 50; i++) {
      s = applyLogLine(s, line({ summary: `line ${i}` }));
    }
    expect(s.logs.length).toBe(LOG_RING_CAPACITY);
    expect(s.logs[s.logs.length - 1]?.summary).toBe(`line ${LOG_RING_CAPACITY + 49}`);
  });
});

describe("PipelineStore — subscribe / getSnapshot", () => {
  it("notifies subscribers on event apply", () => {
    const store = new PipelineStore();
    let calls = 0;
    const unsub = store.subscribe(() => calls++);
    store.applyEvent(ev.pipelineStarted(["01a"]));
    store.applyEvent(ev.phaseStarted("01a"));
    expect(calls).toBe(2);
    expect(store.getSnapshot().pipelineStatus).toBe("running");
    unsub();
    store.applyEvent(ev.phaseCompleted("01a"));
    expect(calls).toBe(2); // no extra call after unsubscribe
  });

  it("setBudget updates the snapshot cost cap", () => {
    const store = new PipelineStore();
    store.setBudget(20);
    expect(store.getSnapshot().cost.max_budget_usd).toBe(20);
  });
});
