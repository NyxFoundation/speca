import { appendFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { render } from "ink-testing-library";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { Dashboard } from "../src/components/Dashboard.js";
import { PHASE_STATUS_GLYPH } from "../src/components/PhaseRow.js";
import { buildAttachSnapshot, scanAttachState } from "../src/lib/pipeline/attach.js";
import { startLogWatcher } from "../src/lib/pipeline/log-watcher.js";
import { PipelineStore } from "../src/lib/pipeline/store.js";

let cwd: string;
beforeEach(() => {
  cwd = mkdtempSync(join(tmpdir(), "speca-attach-render-"));
});
afterEach(() => {
  rmSync(cwd, { recursive: true, force: true });
});

function writePartial(dir: string, name: string, items: number): void {
  const list = Array.from({ length: items }, (_, i) => ({ property_id: `PROP-r-${i}` }));
  writeFileSync(
    join(dir, name),
    JSON.stringify({ reviewed_items: list, metadata: { item_count: items } }),
  );
}

async function seededStore(): Promise<PipelineStore> {
  const scan = await scanAttachState({ cwd });
  const store = new PipelineStore();
  store.seedSnapshot(buildAttachSnapshot(scan, Date.now()));
  return store;
}

describe("speca attach — read-only dashboard render (#27)", () => {
  it("renders phase rows reconstructed from on-disk PARTIALs", async () => {
    const outputs = join(cwd, "outputs");
    mkdirSync(outputs, { recursive: true });
    writePartial(outputs, "01b_PARTIAL_W0B0_1699000000.json", 4);
    writePartial(outputs, "03_PARTIAL_W1B2_1700000000.json", 7);

    const store = await seededStore();
    const ui = render(
      createElement(Dashboard, { store, cwd, readOnly: true, title: "speca attach" }),
    );
    const out = ui.lastFrame() ?? "";
    // Ink may soft-wrap the header ("speca" / "attach" on separate lines)
    // under the test terminal width — assert on the title word, not the
    // exact two-word sequence.
    expect(out).toContain("attach");
    expect(out).toContain("01b");
    expect(out).toContain("Subgraph Extraction");
    expect(out).toContain("03");
    expect(out).toContain("Audit Map");
    // Fresh mtimes → both phases render as running.
    expect(out).toContain(PHASE_STATUS_GLYPH.running);
    ui.unmount();
  });

  it("hides the stop / force keybindings and shows the read-only marker", async () => {
    const outputs = join(cwd, "outputs");
    mkdirSync(outputs, { recursive: true });
    writePartial(outputs, "04_PARTIAL_W0B0_1700000000.json", 1);

    const store = await seededStore();
    const ui = render(
      createElement(Dashboard, { store, cwd, readOnly: true, title: "speca attach" }),
    );
    const out = ui.lastFrame() ?? "";
    expect(out).toContain("read-only");
    expect(out).not.toContain("stop");
    expect(out).not.toContain("force");
    // Detach and log-toggle remain available.
    expect(out).toContain("quit");
    expect(out).toContain("toggle log");
    ui.unmount();
  });

  it("integration: a fake run appending log files updates the attached frame in real time", async () => {
    // Simulates the two-terminal acceptance flow: terminal A (`speca run`)
    // keeps writing outputs/ + logs while terminal B (`speca attach`) only
    // watches the same directory.
    const outputs = join(cwd, "outputs");
    const logs = join(outputs, "logs");
    mkdirSync(logs, { recursive: true });
    writePartial(outputs, "03_PARTIAL_W0B0_1700000000.json", 2);
    const logFile = join(logs, "03_w0b0_1700000001.log.jsonl");
    writeFileSync(
      logFile,
      JSON.stringify({ type: "system", message: { subtype: "init", model: "sonnet" } }) + "\n",
    );

    const store = await seededStore();
    const stop = await startLogWatcher({
      dir: logs,
      onLine: (line) => store.applyLog(line),
      pollIntervalMs: 30,
    });
    const ui = render(
      createElement(Dashboard, { store, cwd, readOnly: true, title: "speca attach" }),
    );
    try {
      // Backlog line (already on disk before attach) must be replayed.
      await waitFor(() => (ui.lastFrame() ?? "").includes("system: init"));
      expect(ui.lastFrame()).toContain("[03/W0/B0]");

      // The "run" keeps going: append a new tool_use line after attach.
      appendFileSync(
        logFile,
        JSON.stringify({
          type: "assistant",
          message: { content: [{ type: "tool_use", name: "Grep", input: {} }] },
        }) + "\n",
      );
      await waitFor(() => (ui.lastFrame() ?? "").includes("tool_use: Grep"));
    } finally {
      ui.unmount();
      await stop();
    }
  });
});

async function waitFor(cond: () => boolean, timeoutMs = 5_000): Promise<void> {
  const start = Date.now();
  while (!cond()) {
    if (Date.now() - start > timeoutMs) {
      throw new Error("waitFor: condition not met within timeout");
    }
    await new Promise((r) => setTimeout(r, 25));
  }
}
