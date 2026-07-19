import { appendFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { runAttachCommand } from "../src/commands/attach.js";
import { startLogWatcher } from "../src/lib/pipeline/log-watcher.js";

let cwd: string;
let stdoutCapture: { chunks: string[]; restore(): void };

beforeEach(() => {
  cwd = mkdtempSync(join(tmpdir(), "speca-attach-cmd-"));
  const chunks: string[] = [];
  const orig = process.stdout.write.bind(process.stdout);
  process.stdout.write = ((c: string | Uint8Array): boolean => {
    chunks.push(typeof c === "string" ? c : Buffer.from(c).toString("utf8"));
    return true;
  }) as typeof process.stdout.write;
  stdoutCapture = {
    chunks,
    restore() {
      process.stdout.write = orig;
    },
  };
});
afterEach(() => {
  stdoutCapture.restore();
  rmSync(cwd, { recursive: true, force: true });
});

describe("runAttachCommand (#27)", () => {
  it("exits 0 with a hint when no pipeline artifacts exist", async () => {
    const code = await runAttachCommand({ flags: {}, cwd });
    expect(code).toBe(0);
    const out = stdoutCapture.chunks.join("");
    expect(out).toContain("nothing to attach to");
    expect(out).toContain("speca run");
  });

  it("exits 0 with a hint when outputs/ exists but holds no PARTIALs or logs", async () => {
    mkdirSync(join(cwd, "outputs", "logs"), { recursive: true });
    writeFileSync(join(cwd, "outputs", "TARGET_INFO.json"), "{}");
    const code = await runAttachCommand({ flags: {}, cwd });
    expect(code).toBe(0);
    expect(stdoutCapture.chunks.join("")).toContain("nothing to attach to");
  });

  it("headless --no-tui prints a scan summary and tails backlog + new lines", async () => {
    const outputs = join(cwd, "outputs");
    const logs = join(outputs, "logs");
    mkdirSync(logs, { recursive: true });
    writeFileSync(
      join(outputs, "04_PARTIAL_W0B0_1700000000.json"),
      JSON.stringify({ reviewed_items: [{ property_id: "PROP-a" }], metadata: { item_count: 1 } }),
    );
    const logFile = join(logs, "04_w0b0_1700000001.log.jsonl");
    writeFileSync(
      logFile,
      JSON.stringify({ type: "system", message: { subtype: "init" } }) + "\n",
    );

    const controller = new AbortController();
    // Fake `speca run` in "another terminal": append a line shortly after
    // attach starts, then detach shortly after that.
    setTimeout(() => {
      appendFileSync(
        logFile,
        JSON.stringify({
          type: "assistant",
          message: { content: [{ type: "tool_use", name: "Read", input: {} }] },
        }) + "\n",
      );
    }, 150);
    setTimeout(() => controller.abort(), 800);

    const code = await runAttachCommand({
      flags: { noTui: true },
      cwd,
      signal: controller.signal,
      startLogs: (opts) => startLogWatcher({ ...opts, pollIntervalMs: 30 }),
    });
    expect(code).toBe(0);
    const out = stdoutCapture.chunks.join("");
    expect(out).toContain("speca attach: 1 phase(s) on disk [04(1 partial)]");
    expect(out).toContain("[04/W0/B0] system: init");
    expect(out).toContain("[04/W0/B0] tool_use: Read");
  });

  it("--json emits an attach-summary envelope followed by log records", async () => {
    const outputs = join(cwd, "outputs");
    const logs = join(outputs, "logs");
    mkdirSync(logs, { recursive: true });
    writeFileSync(
      join(outputs, "03_PARTIAL_W2B5_1700000000.json"),
      JSON.stringify({ audit_items: [{ property_id: "PROP-b" }], metadata: { item_count: 1 } }),
    );
    writeFileSync(
      join(logs, "03_w2b5_1700000001.log.jsonl"),
      JSON.stringify({ type: "result", is_error: false, total_cost_usd: 0.01 }) + "\n",
    );

    const controller = new AbortController();
    setTimeout(() => controller.abort(), 600);
    const code = await runAttachCommand({
      flags: { json: true },
      cwd,
      signal: controller.signal,
      startLogs: (opts) => startLogWatcher({ ...opts, pollIntervalMs: 30 }),
    });
    expect(code).toBe(0);

    const records = stdoutCapture.chunks
      .join("")
      .split("\n")
      .filter(Boolean)
      .map((l) => JSON.parse(l) as Record<string, unknown>);
    expect(records[0]?.type).toBe("attach-summary");
    const summary = records[0] as {
      phases: Array<{ id: string; partial_batches: number; items: number; workers: string[] }>;
    };
    expect(summary.phases).toEqual([
      expect.objectContaining({ id: "03", partial_batches: 1, items: 1, workers: ["2"] }),
    ]);
    const logRecords = records.filter((r) => r.type === "log");
    expect(logRecords.length).toBeGreaterThanOrEqual(1);
    expect(logRecords[0]).toMatchObject({
      phase: "03",
      worker: "2",
      batch: "5",
      event_type: "result",
    });
    expect(String(logRecords[0]?.summary)).toContain("result: ok");
  });

  it("read-only guarantee: attach creates nothing on disk — not even outputs/logs/", async () => {
    // #118 follow-up: the logs dir is deliberately NOT pre-created here.
    // The old watcher unconditionally mkdir'd outputs/logs/, which the
    // previous version of this test masked by creating the dir itself.
    const outputs = join(cwd, "outputs");
    mkdirSync(outputs, { recursive: true });
    const partial = join(outputs, "04_PARTIAL_W0B0_1700000000.json");
    const body = JSON.stringify({ reviewed_items: [], metadata: { item_count: 0 } });
    writeFileSync(partial, body);

    const controller = new AbortController();
    setTimeout(() => controller.abort(), 250);
    const code = await runAttachCommand({
      flags: { noTui: true },
      cwd,
      signal: controller.signal,
      rescanIntervalMs: 50,
      startLogs: (opts) => startLogWatcher({ ...opts, pollIntervalMs: 30 }),
    });
    expect(code).toBe(0);

    const { readFileSync, readdirSync } = await import("node:fs");
    expect(readFileSync(partial, "utf8")).toBe(body);
    // The single strongest assertion: outputs/ holds exactly what the fake
    // run wrote — attach created no logs dir, no state files, nothing.
    expect(readdirSync(outputs)).toEqual(["04_PARTIAL_W0B0_1700000000.json"]);
  });

  it("starts the log tail late when outputs/logs/ appears after attach (#118 follow-up)", async () => {
    const outputs = join(cwd, "outputs");
    mkdirSync(outputs, { recursive: true });
    writeFileSync(
      join(outputs, "04_PARTIAL_W0B0_1700000000.json"),
      JSON.stringify({ reviewed_items: [{ property_id: "PROP-late" }], metadata: { item_count: 1 } }),
    );
    // NOTE: no logs dir yet — the run has not produced its first log write.

    const controller = new AbortController();
    setTimeout(() => {
      // The run's first log write lands AFTER attach started watching.
      const logs = join(outputs, "logs");
      mkdirSync(logs, { recursive: true });
      writeFileSync(
        join(logs, "04_w0b0_1700000001.log.jsonl"),
        JSON.stringify({ type: "system", message: { subtype: "init" } }) + "\n",
      );
    }, 150);
    setTimeout(() => controller.abort(), 900);

    const code = await runAttachCommand({
      flags: { noTui: true },
      cwd,
      signal: controller.signal,
      rescanIntervalMs: 50,
      startLogs: (opts) => startLogWatcher({ ...opts, pollIntervalMs: 30 }),
    });
    expect(code).toBe(0);
    const out = stdoutCapture.chunks.join("");
    expect(out).toContain("[04/W0/B0] system: init");
  });

  it("SIGTERM detaches cleanly with exit 0 (#118 follow-up)", async () => {
    // No AbortSignal seam here on purpose: this exercises the real
    // process-signal path. `process.emit` invokes the listener directly,
    // which also works on Windows where the OS never delivers SIGTERM.
    const outputs = join(cwd, "outputs");
    const logs = join(outputs, "logs");
    mkdirSync(logs, { recursive: true });
    writeFileSync(
      join(outputs, "04_PARTIAL_W0B0_1700000000.json"),
      JSON.stringify({ reviewed_items: [{ property_id: "PROP-t" }], metadata: { item_count: 1 } }),
    );
    writeFileSync(
      join(logs, "04_w0b0_1700000001.log.jsonl"),
      JSON.stringify({ type: "system", message: { subtype: "init" } }) + "\n",
    );

    const pending = runAttachCommand({
      flags: { noTui: true },
      cwd,
      rescanIntervalMs: 50,
      startLogs: (opts) => startLogWatcher({ ...opts, pollIntervalMs: 30 }),
    });
    // Give the tail a beat to arm, then deliver SIGTERM.
    await new Promise((r) => setTimeout(r, 300));
    process.emit("SIGTERM" as NodeJS.Signals);
    const code = await pending;
    expect(code).toBe(0);
    // The handler deregistered itself — no listener leak across tests.
    expect(process.listenerCount("SIGTERM")).toBe(0);
    expect(process.listenerCount("SIGINT")).toBe(0);
  });
});
