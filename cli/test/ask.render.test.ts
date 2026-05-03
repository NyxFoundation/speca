import { render } from "ink-testing-library";
import { createElement } from "react";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { AskChat } from "../src/components/AskChat.js";
import type { ParsedEvent } from "../src/lib/claude-session/spawn.js";

let workDir: string;

beforeEach(async () => {
  workDir = await fs.mkdtemp(join(tmpdir(), "speca-ask-render-test-"));
});

afterEach(async () => {
  // The chat component persists session.json on its own async tail (we don't
  // await it from inside the test). Give it a moment to settle so rmdir
  // doesn't race the writer on macOS (ENOTEMPTY otherwise). `maxRetries`
  // is the Node 16+ way to soak up that residual race on Windows too.
  await new Promise((r) => setTimeout(r, 50));
  await fs.rm(workDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 50 });
});

function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Build a fake spawnAsk that replays a canned event stream. The event order
 * matches what real `claude --output-format stream-json` produces.
 */
function fakeSpawn(events: ParsedEvent[]) {
  return async () => ({
    pid: 1,
    kill: () => {},
    events: (async function* () {
      for (const ev of events) {
        // Yield asynchronously so React has a chance to render between chunks.
        await delay(1);
        yield ev;
      }
    })() as AsyncIterable<ParsedEvent>,
  });
}

describe("<AskChat /> initial frame", () => {
  it("renders the placeholder text when there are no messages yet", async () => {
    const { lastFrame, unmount } = render(
      createElement(AskChat, {
        finding: null,
        projectRoot: workDir,
      }),
    );
    // Wait one tick for the loadSession promise to resolve.
    await delay(20);
    const frame = lastFrame();
    expect(frame).toContain("speca ask");
    expect(frame).toContain("Ask a question");
    expect(frame).toContain("session: new");
    unmount();
  });

  it("shows the finding label in the status bar when one is provided", async () => {
    const { lastFrame, unmount } = render(
      createElement(AskChat, {
        finding: { property_id: "PROP-render-1", severity: "MED" },
        findingLabel: "PROP-render-1 (MED)",
        projectRoot: workDir,
      }),
    );
    await delay(20);
    const frame = lastFrame();
    expect(frame).toContain("PROP-render-1");
    expect(frame).toContain("(MED)");
    unmount();
  });

  it("renders an existing session id (truncated) when --session is given", async () => {
    const { lastFrame, unmount } = render(
      createElement(AskChat, {
        finding: null,
        initialSessionId: "abcdef0123456789-resume",
        projectRoot: workDir,
      }),
    );
    await delay(20);
    const frame = lastFrame();
    // Truncated to 8 chars per the header logic.
    expect(frame).toContain("session: abcdef01");
    unmount();
  });
});

describe("<AskChat /> message rendering", () => {
  it("appends a user message and the streamed assistant reply", async () => {
    const events: ParsedEvent[] = [
      { type: "system", subtype: "init", session_id: "sess-render-1", raw: {} },
      {
        type: "assistant",
        text: "Hello from the fake assistant.",
        session_id: "sess-render-1",
        raw: {},
      },
      { type: "result", subtype: "success", session_id: "sess-render-1", raw: {} },
      { type: "done", code: 0, session_id: "sess-render-1" },
    ];
    const { stdin, lastFrame, unmount } = render(
      createElement(AskChat, {
        finding: { property_id: "PROP-r", severity: "LOW" },
        findingLabel: "PROP-r (LOW)",
        projectRoot: workDir,
        spawnFn: fakeSpawn(events),
      }),
    );
    await delay(20);
    // We start in input mode by default — type a question, then submit via Ctrl-D.
    stdin.write("hi");
    await delay(20);
    // Ctrl-D byte = 0x04
    stdin.write("");
    // Allow the async event iteration AND the post-turn persistSession
    // write to finish before unmount + tmpdir teardown.
    await delay(300);
    const frame = lastFrame() ?? "";
    expect(frame).toContain("You:");
    expect(frame).toContain("hi");
    expect(frame).toContain("Claude:");
    expect(frame).toContain("Hello from the fake assistant.");
    unmount();
    // One more tick so any Promise resolutions queued by unmount drain.
    await delay(50);
  });
});
