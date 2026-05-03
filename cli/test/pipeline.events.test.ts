import { describe, expect, it } from "vitest";
import {
  parsePipelineEvent,
  pipelineEventSchema,
  splitLines,
  type ParseFailure,
} from "../src/lib/pipeline/events.js";

const ts = "2026-05-03T12:00:00.000+00:00";

describe("parsePipelineEvent — happy path", () => {
  it("parses pipeline-started", () => {
    const ev = parsePipelineEvent(
      JSON.stringify({ type: "pipeline-started", ts, phases: ["01a", "01b"], workers: 4, max_concurrent: 8, force: false }),
    );
    expect(ev?.type).toBe("pipeline-started");
    if (ev?.type === "pipeline-started") {
      expect(ev.phases).toEqual(["01a", "01b"]);
      expect(ev.workers).toBe(4);
    }
  });

  it("parses phase-started with optional model", () => {
    const ev = parsePipelineEvent(
      JSON.stringify({ type: "phase-started", ts, phase: "01a", workers: 4, max_concurrent: 8, force: false, model: "sonnet" }),
    );
    expect(ev?.type).toBe("phase-started");
    if (ev?.type === "phase-started") {
      expect(ev.model).toBe("sonnet");
    }
  });

  it("parses phase-started with null model", () => {
    const ev = parsePipelineEvent(
      JSON.stringify({ type: "phase-started", ts, phase: "01a", workers: 4, max_concurrent: 8, force: false, model: null }),
    );
    expect(ev?.type).toBe("phase-started");
  });

  it("parses phase-completed", () => {
    const ev = parsePipelineEvent(
      JSON.stringify({ type: "phase-completed", ts, phase: "01a", duration_s: 12.5, total_results: 28 }),
    );
    if (ev?.type !== "phase-completed") throw new Error("wrong type");
    expect(ev.duration_s).toBe(12.5);
    expect(ev.total_results).toBe(28);
  });

  it("parses phase-failed", () => {
    const ev = parsePipelineEvent(
      JSON.stringify({ type: "phase-failed", ts, phase: "01b", reason: "dependency check failed", duration_s: 0.1 }),
    );
    if (ev?.type !== "phase-failed") throw new Error("wrong type");
    expect(ev.reason).toContain("dependency");
  });

  it("parses budget-exceeded with optional cost fields", () => {
    const ev = parsePipelineEvent(
      JSON.stringify({ type: "budget-exceeded", ts, phase: "03", cost_usd: 9.97, max_budget_usd: 10, duration_s: 600.5 }),
    );
    if (ev?.type !== "budget-exceeded") throw new Error("wrong type");
    expect(ev.cost_usd).toBe(9.97);
    expect(ev.max_budget_usd).toBe(10);
  });

  it("accepts budget-exceeded with null cost (orchestrator may not always populate)", () => {
    const ev = parsePipelineEvent(
      JSON.stringify({ type: "budget-exceeded", ts, phase: "03", cost_usd: null, max_budget_usd: null, duration_s: 600.5 }),
    );
    expect(ev?.type).toBe("budget-exceeded");
  });

  it("parses circuit-breaker-tripped with stats payload", () => {
    const ev = parsePipelineEvent(
      JSON.stringify({
        type: "circuit-breaker-tripped",
        ts,
        phase: "03",
        reason: "consecutive failures >= threshold",
        stats: { consecutive_failures: 5, total_retries: 17 },
        duration_s: 30.1,
      }),
    );
    if (ev?.type !== "circuit-breaker-tripped") throw new Error("wrong type");
    expect(ev.reason).toMatch(/consecutive/);
    expect(ev.stats?.consecutive_failures).toBe(5);
  });

  it("parses pipeline-completed with results map", () => {
    const ev = parsePipelineEvent(
      JSON.stringify({
        type: "pipeline-completed",
        ts,
        phases: ["01a", "01b"],
        results: { "01a": true, "01b": false },
        duration_s: 100,
      }),
    );
    if (ev?.type !== "pipeline-completed") throw new Error("wrong type");
    expect(ev.results["01a"]).toBe(true);
    expect(ev.results["01b"]).toBe(false);
  });
});

describe("parsePipelineEvent — rejects invalid input", () => {
  const failures: ParseFailure[] = [];
  const onWarn = (f: ParseFailure) => failures.push(f);

  it("returns null on empty / whitespace input without warning", () => {
    failures.length = 0;
    expect(parsePipelineEvent("", onWarn)).toBeNull();
    expect(parsePipelineEvent("   ", onWarn)).toBeNull();
    expect(failures).toHaveLength(0);
  });

  it("returns null on malformed JSON and warns", () => {
    failures.length = 0;
    expect(parsePipelineEvent("not json", onWarn)).toBeNull();
    expect(failures).toHaveLength(1);
    expect(failures[0]?.reason).toContain("invalid JSON");
  });

  it("returns null on missing required field and warns", () => {
    failures.length = 0;
    expect(
      parsePipelineEvent(JSON.stringify({ type: "phase-started", phase: "01a" }), onWarn),
    ).toBeNull();
    expect(failures).toHaveLength(1);
    expect(failures[0]?.reason).toContain("schema mismatch");
  });

  it("returns null on unknown type discriminator", () => {
    failures.length = 0;
    expect(
      parsePipelineEvent(JSON.stringify({ type: "wat", ts, phase: "01a" }), onWarn),
    ).toBeNull();
    expect(failures).toHaveLength(1);
  });

  it("returns null when stats is the wrong type", () => {
    failures.length = 0;
    expect(
      parsePipelineEvent(
        JSON.stringify({ type: "circuit-breaker-tripped", ts, phase: "03", reason: "x", stats: "not-a-record", duration_s: 1 }),
        onWarn,
      ),
    ).toBeNull();
    expect(failures).toHaveLength(1);
  });
});

describe("pipelineEventSchema discriminator", () => {
  it("narrows to the right event type", () => {
    const result = pipelineEventSchema.safeParse({
      type: "phase-completed",
      ts,
      phase: "01a",
      duration_s: 1,
      total_results: 0,
    });
    expect(result.success).toBe(true);
    if (result.success && result.data.type === "phase-completed") {
      expect(result.data.total_results).toBe(0);
    }
  });
});

describe("splitLines", () => {
  it("splits on \\n and keeps trailing partial line as carry", () => {
    const r = splitLines("a\nb\nc", "");
    expect(r.lines).toEqual(["a", "b"]);
    expect(r.carry).toBe("c");
  });
  it("merges carry from a previous chunk", () => {
    const r1 = splitLines("ab", "");
    const r2 = splitLines("c\nd", r1.carry);
    expect(r2.lines).toEqual(["abc"]);
    expect(r2.carry).toBe("d");
  });
  it("handles \\r\\n line endings (Windows)", () => {
    const r = splitLines("a\r\nb\r\n", "");
    expect(r.lines).toEqual(["a", "b"]);
    expect(r.carry).toBe("");
  });
});
