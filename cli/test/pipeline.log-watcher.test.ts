import { describe, expect, it } from "vitest";
import { parseLogFilename, summariseRawLogLine } from "../src/lib/pipeline/log-watcher.js";

describe("parseLogFilename", () => {
  it("parses the canonical phase_w<n>b<m>_<ts>.log.jsonl pattern", () => {
    const r = parseLogFilename("01a_w0b3_2026-05-03T12-00-00.log.jsonl");
    expect(r).toEqual({ phase: "01a", worker: "0", batch: "3" });
  });

  it("returns null for non-matching names", () => {
    expect(parseLogFilename("garbage.txt")).toBeNull();
    expect(parseLogFilename("01a_extracted.json")).toBeNull();
  });
});

describe("summariseRawLogLine", () => {
  it("summarises an assistant tool_use line", () => {
    const r = summariseRawLogLine({
      type: "assistant",
      message: { content: [{ type: "tool_use", name: "Grep", input: {} }] },
    });
    expect(r?.summary).toBe("tool_use: Grep");
    expect(r?.tool).toBe("Grep");
    expect(r?.severity).toBe("info");
  });

  it("summarises an assistant text line", () => {
    const r = summariseRawLogLine({
      type: "assistant",
      message: { content: [{ type: "text", text: "Hello world" }] },
    });
    expect(r?.summary).toMatch(/^assistant:/);
  });

  it("summarises a system message with model", () => {
    const r = summariseRawLogLine({
      type: "system",
      message: { subtype: "init", model: "claude-sonnet-4-5" },
    });
    expect(r?.summary).toContain("system: init");
    expect(r?.summary).toContain("model=claude-sonnet-4-5");
  });

  it("summarises a result line with cost", () => {
    const r = summariseRawLogLine({ type: "result", is_error: false, total_cost_usd: 0.012345 });
    expect(r?.summary).toContain("result: ok");
    expect(r?.summary).toContain("cost=$0.0123");
    expect(r?.severity).toBe("info");
  });

  it("flags an error result as error severity", () => {
    const r = summariseRawLogLine({ type: "result", is_error: true });
    expect(r?.severity).toBe("error");
  });

  it("returns an error severity for top-level error events", () => {
    const r = summariseRawLogLine({
      type: "error",
      error: { type: "rate_limit_error", message: "429 too many requests" },
    });
    expect(r?.severity).toBe("error");
    expect(r?.summary).toMatch(/rate_limit_error/);
  });

  it("returns null for non-objects", () => {
    expect(summariseRawLogLine(null)).toBeNull();
    expect(summariseRawLogLine("foo")).toBeNull();
  });
});
