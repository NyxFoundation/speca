import { describe, it, expect } from "vitest";
import { parseEventLine, PipelineEvent } from "../src/lib/events.js";

describe("parseEventLine", () => {
  it("parses a pipeline-started event", () => {
    const line = JSON.stringify({
      type: "pipeline-started",
      ts: "2026-01-01T00:00:00.000Z",
      phases: ["01a", "01b"],
      workers: 4,
      max_concurrent: 8,
      force: false,
    });
    const event = parseEventLine(line);
    expect(event).not.toBeNull();
    expect(event!.type).toBe("pipeline-started");
    if (event!.type === "pipeline-started") {
      expect(event!.phases).toEqual(["01a", "01b"]);
      expect(event!.workers).toBe(4);
    }
  });

  it("parses a phase-started event", () => {
    const line = JSON.stringify({
      type: "phase-started",
      ts: "2026-01-01T00:00:01.000Z",
      phase: "01a",
      workers: 4,
      max_concurrent: 8,
      force: false,
      model: "sonnet",
    });
    const event = parseEventLine(line);
    expect(event).not.toBeNull();
    expect(event!.type).toBe("phase-started");
    if (event!.type === "phase-started") {
      expect(event!.phase).toBe("01a");
      expect(event!.model).toBe("sonnet");
    }
  });

  it("parses a phase-completed event", () => {
    const line = JSON.stringify({
      type: "phase-completed",
      ts: "2026-01-01T00:10:00.000Z",
      phase: "01a",
      duration_s: 600,
      total_results: 42,
    });
    const event = parseEventLine(line);
    expect(event).not.toBeNull();
    if (event!.type === "phase-completed") {
      expect(event!.total_results).toBe(42);
      expect(event!.duration_s).toBe(600);
    }
  });

  it("parses a phase-failed event", () => {
    const line = JSON.stringify({
      type: "phase-failed",
      ts: "2026-01-01T00:05:00.000Z",
      phase: "03",
      reason: "Missing TARGET_INFO.json",
      duration_s: 300,
    });
    const event = parseEventLine(line);
    expect(event).not.toBeNull();
    if (event!.type === "phase-failed") {
      expect(event!.reason).toBe("Missing TARGET_INFO.json");
    }
  });

  it("parses a budget-exceeded event", () => {
    const line = JSON.stringify({
      type: "budget-exceeded",
      ts: "2026-01-01T01:00:00.000Z",
      phase: "03",
      cost_usd: 15.5,
      max_budget_usd: 10.0,
      duration_s: 3600,
    });
    const event = parseEventLine(line);
    expect(event).not.toBeNull();
    if (event!.type === "budget-exceeded") {
      expect(event!.cost_usd).toBe(15.5);
      expect(event!.max_budget_usd).toBe(10.0);
    }
  });

  it("parses a circuit-breaker-tripped event", () => {
    const line = JSON.stringify({
      type: "circuit-breaker-tripped",
      ts: "2026-01-01T00:30:00.000Z",
      phase: "03",
      reason: "5 consecutive failures",
      duration_s: 1800,
    });
    const event = parseEventLine(line);
    expect(event).not.toBeNull();
    if (event!.type === "circuit-breaker-tripped") {
      expect(event!.reason).toContain("consecutive");
    }
  });

  it("parses a pipeline-completed event", () => {
    const line = JSON.stringify({
      type: "pipeline-completed",
      ts: "2026-01-01T02:00:00.000Z",
      phases: ["01a", "01b", "01e"],
      duration_s: 7200,
    });
    const event = parseEventLine(line);
    expect(event).not.toBeNull();
    if (event!.type === "pipeline-completed") {
      expect(event!.phases).toHaveLength(3);
      expect(event!.duration_s).toBe(7200);
    }
  });

  it("returns null for empty line", () => {
    expect(parseEventLine("")).toBeNull();
    expect(parseEventLine("  ")).toBeNull();
  });

  it("returns null for non-JSON", () => {
    expect(parseEventLine("INFO: Starting phase 01a")).toBeNull();
  });

  it("returns null for unknown event type", () => {
    const line = JSON.stringify({ type: "unknown-event", ts: "2026-01-01T00:00:00Z" });
    expect(parseEventLine(line)).toBeNull();
  });

  it("returns null for malformed JSON", () => {
    expect(parseEventLine("{broken json")).toBeNull();
  });
});

describe("PipelineEvent discriminated union", () => {
  it("parses valid event via safeParse", () => {
    const result = PipelineEvent.safeParse({
      type: "phase-started",
      ts: "2026-01-01T00:00:00Z",
      phase: "01a",
      workers: 1,
      max_concurrent: 1,
      force: false,
    });
    expect(result.success).toBe(true);
  });

  it("rejects missing required fields", () => {
    const result = PipelineEvent.safeParse({
      type: "phase-started",
      ts: "2026-01-01T00:00:00Z",
      // missing phase, workers, etc.
    });
    expect(result.success).toBe(false);
  });
});
