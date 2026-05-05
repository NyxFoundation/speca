import { describe, it, expect, beforeEach } from "vitest";
import { mkdtempSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  buildFindingContext,
  loadSession,
  saveSession,
} from "../src/lib/claude-bridge.js";

describe("buildFindingContext", () => {
  it("builds context from a finding", () => {
    const context = buildFindingContext({
      propertyId: "PROP-001",
      classification: "Buffer Overflow",
      severity: "Critical",
      verdict: "Confirmed",
      summary: "Stack overflow in parser",
      reviewerNotes: "Verified in audit",
      codePath: "src/parser.c:42",
      codeSnippet: "void parse() { char buf[10]; gets(buf); }",
    });

    expect(context).toContain("PROP-001");
    expect(context).toContain("Buffer Overflow");
    expect(context).toContain("Critical");
    expect(context).toContain("Stack overflow");
    expect(context).toContain("src/parser.c:42");
    expect(context).toContain("gets(buf)");
  });

  it("omits empty sections", () => {
    const context = buildFindingContext({
      propertyId: "PROP-002",
      classification: "XSS",
      severity: "Medium",
      verdict: "",
      summary: "Reflected XSS",
      reviewerNotes: "",
      codePath: "",
      codeSnippet: "",
    });

    expect(context).toContain("PROP-002");
    expect(context).not.toContain("Reviewer Notes");
    expect(context).not.toContain("Code Location");
    expect(context).not.toContain("Proof Trace");
  });

  it("truncates context over 50KB", () => {
    const context = buildFindingContext({
      propertyId: "PROP-003",
      classification: "Test",
      severity: "Low",
      verdict: "",
      summary: "x".repeat(60000),
      reviewerNotes: "",
      codePath: "",
      codeSnippet: "",
    });

    expect(Buffer.byteLength(context, "utf8")).toBeLessThanOrEqual(51300); // 50KB + truncation notice
    expect(context).toContain("[Context truncated to 50KB]");
  });
});

describe("session persistence", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "speca-session-"));
  });

  it("returns empty sessionId for missing file", async () => {
    const info = await loadSession(tmpDir);
    expect(info.sessionId).toBe("");
    expect(info.projectDir).toBe(tmpDir);
  });

  it("saves and loads session", async () => {
    await saveSession({ sessionId: "test-session-123", projectDir: tmpDir });

    const raw = JSON.parse(readFileSync(join(tmpDir, ".speca", "session.json"), "utf8"));
    expect(raw.sessionId).toBe("test-session-123");

    const loaded = await loadSession(tmpDir);
    expect(loaded.sessionId).toBe("test-session-123");
  });

  it("handles malformed session file", async () => {
    const { writeFileSync, mkdirSync } = await import("node:fs");
    mkdirSync(join(tmpDir, ".speca"), { recursive: true });
    writeFileSync(join(tmpDir, ".speca", "session.json"), "not json");

    const info = await loadSession(tmpDir);
    expect(info.sessionId).toBe("");
  });
});
