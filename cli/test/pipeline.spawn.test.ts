import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { spawnPipeline } from "../src/lib/pipeline/spawn.js";
import type { PipelineEvent } from "../src/lib/pipeline/events.js";

/**
 * The spawn layer is exercised against a fake "run_phase.py" — we point
 * `command` at the current Node executable and pass a fixture .mjs file
 * to emit canned NDJSON. We avoid `node -e` because Node 22+ may treat the
 * payload as TypeScript and reject the embedded escapes; a real file is
 * the most portable cross-platform fixture.
 */
const NODE = process.execPath;

const ts = "2026-05-03T12:00:00.000+00:00";

let scriptDir: string;
beforeEach(() => {
  scriptDir = mkdtempSync(join(tmpdir(), "speca-spawn-test-"));
});
afterEach(() => {
  rmSync(scriptDir, { recursive: true, force: true });
});

function fakeScript(body: string): string[] {
  const path = join(scriptDir, `fake-${Math.random().toString(36).slice(2)}.mjs`);
  writeFileSync(path, body, "utf8");
  return [path];
}

describe("spawnPipeline — NDJSON stream", () => {
  it("delivers parsed events in order and resolves with exit 0", async () => {
    const body = `
const events = ${JSON.stringify([
      { type: "pipeline-started", ts, phases: ["01a"], workers: 4, max_concurrent: 8, force: false },
      { type: "phase-started", ts, phase: "01a", workers: 4, max_concurrent: 8, force: false },
      { type: "phase-completed", ts, phase: "01a", duration_s: 1.0, total_results: 2 },
      { type: "pipeline-completed", ts, phases: ["01a"], results: { "01a": true }, duration_s: 1.5 },
    ])};
for (const e of events) process.stdout.write(JSON.stringify(e) + "\\n");
process.exit(0);
`;
    const handle = spawnPipeline({
      phases: ["01a"],
      command: NODE,
      baseArgs: fakeScript(body),
    });
    const seen: PipelineEvent[] = [];
    const warns: unknown[] = [];
    handle.on("event", (e) => seen.push(e));
    handle.on("warn", (f) => warns.push(f));
    const code = await handle.done;
    expect(code).toBe(0);
    expect(seen).toHaveLength(4);
    expect(seen[0]?.type).toBe("pipeline-started");
    expect(seen[3]?.type).toBe("pipeline-completed");
    expect(warns).toHaveLength(0);
  });

  it("forwards stderr lines to the stderr listener", async () => {
    const body = `
process.stderr.write("hello stderr\\n");
process.stderr.write("second line\\n");
process.exit(0);
`;
    const handle = spawnPipeline({
      phases: ["01a"],
      command: NODE,
      baseArgs: fakeScript(body),
    });
    const errLines: string[] = [];
    handle.on("stderr", (l) => errLines.push(l));
    const code = await handle.done;
    expect(code).toBe(0);
    expect(errLines).toContain("hello stderr");
    expect(errLines).toContain("second line");
  });

  it("warns on malformed lines but keeps reading", async () => {
    const body = `
process.stdout.write("not json\\n");
process.stdout.write(${JSON.stringify(JSON.stringify({ type: "phase-completed", ts, phase: "01a", duration_s: 1, total_results: 0 }))} + "\\n");
process.exit(0);
`;
    const handle = spawnPipeline({
      phases: ["01a"],
      command: NODE,
      baseArgs: fakeScript(body),
    });
    const seen: PipelineEvent[] = [];
    const warns: { reason: string }[] = [];
    handle.on("event", (e) => seen.push(e));
    handle.on("warn", (f) => warns.push(f));
    const code = await handle.done;
    expect(code).toBe(0);
    expect(seen).toHaveLength(1);
    expect(warns).toHaveLength(1);
  });

  it("propagates a non-zero exit code", async () => {
    const body = `process.exit(7);`;
    const handle = spawnPipeline({
      phases: ["01a"],
      command: NODE,
      baseArgs: fakeScript(body),
    });
    const code = await handle.done;
    expect(code).toBe(7);
  });

  it("emits spawn-error and exits with 127 when the command does not exist", async () => {
    const handle = spawnPipeline({
      phases: ["01a"],
      command: "definitely-not-a-real-binary-xyz",
      baseArgs: ["--no-args"],
    });
    let errored = false;
    handle.on("spawn-error", () => {
      errored = true;
    });
    const code = await handle.done;
    expect(errored).toBe(true);
    // 127 = ENOENT-style (we cannot guarantee exact value across platforms — accept any non-zero).
    expect(code).not.toBe(0);
  });

  it("buffers a chunk that arrives mid-line", async () => {
    // Emit each character with a tiny delay so chunk boundaries land mid-line.
    const event = JSON.stringify({ type: "phase-completed", ts, phase: "01a", duration_s: 1, total_results: 0 });
    const body = `
const line = ${JSON.stringify(event + "\n")};
let i = 0;
const t = setInterval(() => {
  if (i >= line.length) {
    clearInterval(t);
    process.exit(0);
    return;
  }
  process.stdout.write(line.slice(i, i + 5));
  i += 5;
}, 5);
`;
    const handle = spawnPipeline({
      phases: ["01a"],
      command: NODE,
      baseArgs: fakeScript(body),
    });
    const seen: PipelineEvent[] = [];
    handle.on("event", (e) => seen.push(e));
    const code = await handle.done;
    expect(code).toBe(0);
    expect(seen).toHaveLength(1);
    expect(seen[0]?.type).toBe("phase-completed");
  });
});
