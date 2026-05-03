import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { runRunCommand } from "../src/commands/run.js";
import { spawnPipeline } from "../src/lib/pipeline/spawn.js";
import { startLogWatcher } from "../src/lib/pipeline/log-watcher.js";

const NODE = process.execPath;
const ts = "2026-05-03T12:00:00.000+00:00";

let cwd: string;
let scriptDir: string;
beforeEach(() => {
  cwd = mkdtempSync(join(tmpdir(), "speca-run-"));
  scriptDir = mkdtempSync(join(tmpdir(), "speca-run-script-"));
});
afterEach(() => {
  rmSync(cwd, { recursive: true, force: true });
  rmSync(scriptDir, { recursive: true, force: true });
});

/**
 * Build a fake spawnPipeline that uses Node to emit a canned NDJSON stream
 * mimicking the dependency-failure path (`speca run --phase 01b` in a cwd
 * with no upstream outputs would produce phase-failed + exit 1).
 *
 * We materialise the fixture as a real .mjs file rather than passing it via
 * `node -e` because Node 22+ may attempt to evaluate the payload as
 * TypeScript and reject embedded escapes.
 */
function fakeSpawnDependencyFailure(): typeof spawnPipeline {
  return ((opts) => {
    const phases = opts.phases ?? [opts.target ?? "01b"];
    const event1 = {
      type: "pipeline-started",
      ts,
      phases,
      workers: opts.workers ?? 4,
      max_concurrent: opts.maxConcurrent ?? 8,
      force: opts.force ?? false,
    };
    const event2 = {
      type: "phase-failed",
      ts,
      phase: phases[0],
      reason: "dependency check failed",
      duration_s: 0.1,
    };
    const event3 = {
      type: "pipeline-completed",
      ts,
      phases,
      results: { [phases[0]!]: false },
      duration_s: 0.2,
    };
    const body = `const events = ${JSON.stringify([event1, event2, event3])};
for (const e of events) process.stdout.write(JSON.stringify(e) + "\\n");
process.exit(1);
`;
    const path = join(scriptDir, `fake-${Math.random().toString(36).slice(2)}.mjs`);
    writeFileSync(path, body, "utf8");
    return spawnPipeline({
      ...opts,
      command: NODE,
      baseArgs: [path],
    });
  }) as typeof spawnPipeline;
}

describe("runRunCommand — headless flow", () => {
  it("returns an error code when neither --phase nor --target is provided", async () => {
    const code = await runRunCommand({ flags: {}, cwd });
    expect(code).toBe(2);
  });

  it("fakes a dependency-failure NDJSON stream and exits non-zero", async () => {
    // Force headless mode by passing --no-tui (also avoids stdout.isTTY confusion).
    const code = await runRunCommand({
      flags: { phase: ["01b"], noTui: true },
      cwd,
      spawn: fakeSpawnDependencyFailure(),
      // Skip log watcher in tests (it tries to mkdir; allowed but unnecessary here).
      startLogs: async () => async () => {},
    });
    expect(code).toBe(1);
  });

  it("--json mode emits one JSON object per line on stdout", async () => {
    const lines: string[] = [];
    const origWrite = process.stdout.write.bind(process.stdout);
    process.stdout.write = ((chunk: string | Uint8Array): boolean => {
      const text = typeof chunk === "string" ? chunk : Buffer.from(chunk).toString("utf8");
      lines.push(text);
      return true;
    }) as typeof process.stdout.write;
    try {
      const code = await runRunCommand({
        flags: { phase: ["01b"], json: true },
        cwd,
        spawn: fakeSpawnDependencyFailure(),
        startLogs: async () => async () => {},
      });
      expect(code).toBe(1);
    } finally {
      process.stdout.write = origWrite;
    }
    const joined = lines.join("");
    const events = joined.split("\n").filter(Boolean).map((l) => JSON.parse(l));
    expect(events).toHaveLength(3);
    expect(events[0].type).toBe("pipeline-started");
    expect(events[1].type).toBe("phase-failed");
    expect(events[2].type).toBe("pipeline-completed");
  });

  it("falls back to startLogs default without crashing if a watcher fails", async () => {
    // Pass a startLogs that throws — the run should still complete.
    const code = await runRunCommand({
      flags: { phase: ["01b"], noTui: true },
      cwd,
      spawn: fakeSpawnDependencyFailure(),
      startLogs: (async () => {
        throw new Error("watcher unavailable");
      }) as typeof startLogWatcher,
    });
    expect(code).toBe(1);
  });
});
