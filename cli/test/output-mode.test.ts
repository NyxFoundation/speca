import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  emitJson,
  getOutputMode,
  printNoTui,
} from "../src/lib/io/output-mode.js";

describe("getOutputMode", () => {
  it("--json wins over everything else", () => {
    expect(getOutputMode({ json: true }, { isTTY: true })).toBe("json");
    expect(getOutputMode({ json: true, noTui: true }, { isTTY: false })).toBe("json");
  });

  it("--no-tui forces no-tui even on a TTY", () => {
    expect(getOutputMode({ noTui: true }, { isTTY: true })).toBe("no-tui");
  });

  it("non-TTY stdout falls back to no-tui", () => {
    expect(getOutputMode({}, { isTTY: false })).toBe("no-tui");
  });

  it("TTY stdout with no flags yields tui", () => {
    expect(getOutputMode({}, { isTTY: true })).toBe("tui");
  });

  it("SPECA_FORCE_TUI overrides the TTY check", () => {
    expect(getOutputMode({}, { isTTY: false, forceTui: true })).toBe("tui");
  });

  it("--json beats SPECA_FORCE_TUI", () => {
    expect(getOutputMode({ json: true }, { isTTY: false, forceTui: true })).toBe("json");
  });

  it("--no-tui beats SPECA_FORCE_TUI", () => {
    expect(getOutputMode({ noTui: true }, { isTTY: true, forceTui: true })).toBe("no-tui");
  });
});

describe("printNoTui", () => {
  let writeSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    writeSpy = vi.spyOn(process.stdout, "write").mockImplementation(() => true);
  });

  afterEach(() => {
    writeSpy.mockRestore();
  });

  it("appends a trailing newline", () => {
    printNoTui("hello");
    expect(writeSpy).toHaveBeenCalledWith("hello\n");
  });
});

describe("emitJson", () => {
  let writeSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    writeSpy = vi.spyOn(process.stdout, "write").mockImplementation(() => true);
  });

  afterEach(() => {
    writeSpy.mockRestore();
  });

  it("stamps an ISO ts when one is not supplied", () => {
    emitJson({ type: "phase-started", phase: "01a" });
    const written = writeSpy.mock.calls[0][0] as string;
    expect(written.endsWith("\n")).toBe(true);
    const parsed = JSON.parse(written.trim());
    expect(parsed.type).toBe("phase-started");
    expect(parsed.phase).toBe("01a");
    expect(typeof parsed.ts).toBe("string");
    // Loose ISO 8601 check: starts with YYYY-MM-DD.
    expect(parsed.ts).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it("preserves a caller-supplied ts", () => {
    emitJson({ type: "x", ts: "2026-01-01T00:00:00.000Z" });
    const written = writeSpy.mock.calls[0][0] as string;
    const parsed = JSON.parse(written.trim());
    expect(parsed.ts).toBe("2026-01-01T00:00:00.000Z");
  });

  it("falls back to an error envelope when serialisation fails", () => {
    const cycle: Record<string, unknown> = { type: "x" };
    cycle.self = cycle;
    emitJson(cycle);
    const written = writeSpy.mock.calls[0][0] as string;
    const parsed = JSON.parse(written.trim());
    expect(parsed.type).toBe("error");
    expect(typeof parsed.error).toBe("string");
  });
});
