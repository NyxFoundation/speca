import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  buildClaudeArgs,
  parseStreamJsonLine,
  spawnAsk,
  type ParsedEvent,
} from "../src/lib/claude-session/spawn.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FAKE_CLAUDE = join(__dirname, "fixtures", "fake-claude.mjs");

// We invoke the fake via the current Node binary. On Windows, .mjs files are
// not directly executable; on POSIX, even with a shebang, vitest tmp env may
// strip exec bits. So we always go through `process.execPath` + the script
// path, which works uniformly.
async function runFake(opts: { prompt: string; sessionId?: string }) {
  const handle = await spawnAsk({
    prompt: opts.prompt,
    sessionId: opts.sessionId,
    claudeBin: process.execPath, // node
    extraArgs: [FAKE_CLAUDE],
  });
  const collected: ParsedEvent[] = [];
  for await (const ev of handle.events) {
    collected.push(ev);
    if (ev.type === "done") break;
  }
  return collected;
}

describe("buildClaudeArgs", () => {
  it("emits stream-json + verbose + text input by default", () => {
    const args = buildClaudeArgs(undefined);
    expect(args).toEqual([
      "-p",
      "--input-format",
      "text",
      "--output-format",
      "stream-json",
      "--verbose",
    ]);
  });

  it("appends --resume when a session id is provided", () => {
    const args = buildClaudeArgs("abc123");
    expect(args).toContain("--resume");
    expect(args[args.indexOf("--resume") + 1]).toBe("abc123");
  });

  it("prepends extra args before the flag block (test-only helper)", () => {
    const args = buildClaudeArgs(undefined, ["--foo", "bar"]);
    expect(args.slice(0, 2)).toEqual(["--foo", "bar"]);
    expect(args).toContain("-p");
  });
});

describe("parseStreamJsonLine", () => {
  it("returns null for blank lines", () => {
    expect(parseStreamJsonLine("")).toBeNull();
    expect(parseStreamJsonLine("   ")).toBeNull();
  });

  it("decodes assistant text out of message.content[]", () => {
    const ev = parseStreamJsonLine(
      JSON.stringify({
        type: "assistant",
        session_id: "s-1",
        message: { content: [{ type: "text", text: "hello world" }] },
      }),
    );
    expect(ev?.type).toBe("assistant");
    if (ev?.type === "assistant") {
      expect(ev.text).toBe("hello world");
      expect(ev.session_id).toBe("s-1");
    }
  });

  it("concatenates multiple text content segments", () => {
    const ev = parseStreamJsonLine(
      JSON.stringify({
        type: "assistant",
        message: {
          content: [
            { type: "text", text: "alpha " },
            { type: "tool_use", id: "x", input: {} },
            { type: "text", text: "beta" },
          ],
        },
      }),
    );
    expect(ev?.type).toBe("assistant");
    if (ev?.type === "assistant") expect(ev.text).toBe("alpha beta");
  });

  it("returns a stream-error wrapper for malformed JSON", () => {
    const ev = parseStreamJsonLine("{ not json");
    expect(ev?.type).toBe("stream-error");
  });

  it("passes unknown event types through as system-shaped", () => {
    const ev = parseStreamJsonLine(JSON.stringify({ type: "no_such_type", foo: 1 }));
    expect(ev?.type).toBe("system");
  });
});

describe("spawnAsk (with fake claude)", () => {
  it("parses the fake's stream-json into typed events", async () => {
    const events = await runFake({ prompt: "what is the meaning of life?" });
    const types = events.map((e) => e.type);
    expect(types).toContain("system");
    expect(types).toContain("assistant");
    expect(types).toContain("result");
    expect(types[types.length - 1]).toBe("done");

    const assistant = events.find((e) => e.type === "assistant");
    expect(assistant?.type).toBe("assistant");
    if (assistant?.type === "assistant") {
      expect(assistant.text.startsWith("echo:")).toBe(true);
    }
  });

  it("propagates --resume so the fake echoes the same session id", async () => {
    const events = await runFake({
      prompt: "second turn",
      sessionId: "preserved-session-id",
    });
    const sysEvent = events.find((e) => e.type === "system");
    expect(sysEvent?.type).toBe("system");
    if (sysEvent?.type === "system") {
      expect(sysEvent.session_id).toBe("preserved-session-id");
    }
    const done = events[events.length - 1];
    expect(done.type).toBe("done");
    if (done.type === "done") {
      expect(done.session_id).toBe("preserved-session-id");
      expect(done.code).toBe(0);
    }
  });

  it("delivers the prompt to the subprocess on stdin", async () => {
    const events = await runFake({ prompt: "stdin-marker-payload" });
    const assistant = events.find((e) => e.type === "assistant");
    expect(assistant?.type).toBe("assistant");
    if (assistant?.type === "assistant") {
      expect(assistant.text).toContain("stdin-marker-payload");
    }
  });
});
