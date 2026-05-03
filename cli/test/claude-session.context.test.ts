import { describe, expect, it } from "vitest";
import {
  buildFindingContext,
  composeAskPrompt,
  DEFAULT_MAX_CONTEXT_BYTES,
  type FindingContextInput,
} from "../src/lib/claude-session/context.js";

const TINY_FINDING: FindingContextInput = {
  property_id: "PROP-test-001",
  severity: "HIGH",
  summary: "short summary",
};

describe("buildFindingContext", () => {
  it("renders a minimal finding without truncation", () => {
    const out = buildFindingContext(TINY_FINDING);
    expect(out.truncated).toBe(false);
    expect(out.truncatedFields).toEqual([]);
    expect(out.prompt).toContain("<system-context>");
    expect(out.prompt).toContain("property_id: PROP-test-001");
    expect(out.prompt).toContain("severity: HIGH");
    expect(out.prompt).toContain("short summary");
    expect(out.bytes).toBeGreaterThan(0);
    expect(out.bytes).toBeLessThan(DEFAULT_MAX_CONTEXT_BYTES);
  });

  it("renders a CodeScope object as a bullet list of locations", () => {
    const finding: FindingContextInput = {
      property_id: "PROP-X",
      code_path: {
        locations: [
          {
            file: "src/foo.ts",
            symbol: "bar",
            line_range: { start: 10, end: 20 },
            role: "primary",
          },
          {
            file: "src/foo.ts",
            symbol: "baz",
            line_range: { start: 30, end: 35 },
            role: "callee",
          },
        ],
      },
    };
    const out = buildFindingContext(finding);
    expect(out.prompt).toContain("- src/foo.ts::bar:10-20");
    expect(out.prompt).toContain("- src/foo.ts::baz:30-35 (callee)");
  });

  it("does not truncate at 49.9KB cap when content fits", () => {
    // A finding well under the cap regardless of how generous the cap is.
    const finding: FindingContextInput = {
      property_id: "PROP-borderline",
      severity: "MED",
      summary: "x".repeat(500),
      proof_trace: "y".repeat(500),
    };
    const out = buildFindingContext(finding, { maxBytes: 49_900 });
    expect(out.truncated).toBe(false);
    expect(out.bytes).toBeLessThanOrEqual(49_900);
    // Banner must NOT be present.
    expect(out.prompt).not.toContain("Code context truncated");
  });

  it("smart-truncates when total payload exceeds the cap (50.1KB → fits)", () => {
    // Build a finding whose verbatim render would exceed 50KB. The proof_trace
    // is the longest field; we expect it to get clipped first.
    const big = "BIG_SECTION_LINE\n".repeat(4_000); // ~64KB
    const finding: FindingContextInput = {
      property_id: "PROP-overflow",
      severity: "CRIT",
      summary: "summary that survives",
      proof_trace: big,
      attack_scenario: "x".repeat(2_000),
    };
    const out = buildFindingContext(finding, { maxBytes: 50_100 });
    expect(out.truncated).toBe(true);
    expect(out.bytes).toBeLessThanOrEqual(50_100);
    expect(out.prompt).toContain("Code context truncated");
    expect(out.truncatedFields).toContain("proof_trace");
    // Identifier survived.
    expect(out.prompt).toContain("PROP-overflow");
    expect(out.prompt).toContain("summary that survives");
  });

  it("falls back to id-only output when even minimal clipping does not fit", () => {
    // Cap so tight (300 bytes) that we are forced into the last-resort branch.
    const finding: FindingContextInput = {
      property_id: "PROP-tightcap",
      severity: "HIGH",
      summary: "s".repeat(2_000),
      proof_trace: "p".repeat(2_000),
      attack_scenario: "a".repeat(2_000),
    };
    const out = buildFindingContext(finding, { maxBytes: 600 });
    expect(out.truncated).toBe(true);
    expect(out.prompt).toContain("PROP-tightcap");
  });

  it("uses 50_000 as the default cap", () => {
    expect(DEFAULT_MAX_CONTEXT_BYTES).toBe(50_000);
  });
});

describe("composeAskPrompt", () => {
  it("returns the bare question when no finding is provided", () => {
    const r = composeAskPrompt(null, "what is going on?");
    expect(r.context).toBeNull();
    expect(r.prompt).toBe("what is going on?");
  });

  it("prefixes the rendered context to the question", () => {
    const r = composeAskPrompt(TINY_FINDING, "explain this");
    expect(r.context).not.toBeNull();
    expect(r.prompt.startsWith("<system-context>")).toBe(true);
    expect(r.prompt.endsWith("explain this")).toBe(true);
  });

  it("propagates the maxBytes option to the context builder", () => {
    const finding: FindingContextInput = {
      property_id: "PROP-x",
      summary: "z".repeat(5_000),
    };
    const r = composeAskPrompt(finding, "hi", { maxBytes: 800 });
    expect(r.context?.truncated).toBe(true);
    expect((r.context?.bytes ?? 0)).toBeLessThanOrEqual(800);
  });
});
