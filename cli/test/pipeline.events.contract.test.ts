/**
 * Cross-language contract test: every event the Python emitter produces is
 * accepted by the auto-generated TS Zod schema, and every TS event-type
 * literal is reachable from a Python emitter call.
 *
 * Skipped automatically when `uv` is not on PATH (so contributors without a
 * Python toolchain can still run `npm test`). The CI job that runs this
 * file installs uv + uv sync, so the test always executes in CI.
 *
 * We DO NOT fall back to bare `python3` — the contract is meaningless
 * without the project's Pydantic deps, and a bare interpreter on Windows
 * pre-installed without our venv would silently mask the real failure.
 */
import { execFileSync, spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  parsePipelineEvent,
  pipelineEventSchema,
  type PipelineEventType,
} from "../src/lib/pipeline/events.js";

const repoRoot = resolve(__dirname, "..", "..");

function uvAvailable(): boolean {
  try {
    const out = spawnSync("uv", ["--version"], { cwd: repoRoot, stdio: "pipe" });
    return out.status === 0;
  } catch {
    return false;
  }
}

const UV_OK = uvAvailable();

/**
 * Run the harness via `uv run python` (no `3` suffix — Windows venvs ship
 * `python.exe`, POSIX venvs symlink `python` too, and uv resolves either
 * way through the active project environment). Throws if uv exits non-zero
 * — the test should fail loudly so a missing dep surfaces.
 */
function runViaUv(harness: string): string {
  return execFileSync("uv", ["run", "python", "-c", harness], {
    cwd: repoRoot,
    encoding: "utf8",
  });
}

const ALL_EVENT_TYPES: PipelineEventType[] = [
  "pipeline-started",
  "phase-started",
  "phase-completed",
  "phase-failed",
  "budget-exceeded",
  "circuit-breaker-tripped",
  "pipeline-completed",
  "warning",
];

describe.skipIf(!UV_OK)("Python ↔ TS event contract", () => {
  it("Python emitter output validates against the TS Zod schema for every event type", () => {
    // One-shot Python harness that emits one of every known event type to
    // stdout. Living inline keeps the test self-contained.
    const harness = `
import sys
sys.path.insert(0, ${JSON.stringify(resolve(repoRoot, "scripts"))})
from orchestrator.json_events import JsonEventEmitter

e = JsonEventEmitter(enabled=True)
e.emit("pipeline-started", phases=["01a"], workers=4, max_concurrent=8, force=False)
e.emit("phase-started", phase="01a", workers=4, max_concurrent=8, force=False, model="sonnet")
e.emit("phase-completed", phase="01a", duration_s=1.5, total_results=10)
e.emit("phase-failed", phase="01b", reason="dependency check failed", duration_s=0.1)
e.emit("budget-exceeded", phase="03", cost_usd=9.9, max_budget_usd=10.0, duration_s=600.0)
e.emit("circuit-breaker-tripped", phase="03", reason="too many failures", stats={"consecutive_failures": 5}, duration_s=30.0)
e.emit("pipeline-completed", phases=["01a"], results={"01a": True}, duration_s=2.0)
e.emit("warning", phase="02c", message="MCP servers not configured: tree_sitter")
`;
    const stdout = runViaUv(harness);

    const lines = stdout.split("\n").filter((l) => l.trim().length > 0);
    expect(lines.length).toBe(ALL_EVENT_TYPES.length);

    const observedTypes = new Set<string>();
    for (const line of lines) {
      const parsed = pipelineEventSchema.safeParse(JSON.parse(line));
      if (!parsed.success) {
        throw new Error(
          `Zod rejected Python emitter output:\nline=${line}\nerrors=${JSON.stringify(parsed.error.issues, null, 2)}`,
        );
      }
      observedTypes.add(parsed.data.type);
    }
    // Every event-type literal in the TS union has a corresponding Python emit.
    for (const t of ALL_EVENT_TYPES) {
      expect(observedTypes.has(t)).toBe(true);
    }
  }, 30_000);

  it("parsePipelineEvent handles real Python output line-by-line", () => {
    // Same harness, but driven through the public parser to exercise the
    // exact code path the dashboard takes (including the warn callback).
    const harness = `
import sys
sys.path.insert(0, ${JSON.stringify(resolve(repoRoot, "scripts"))})
from orchestrator.json_events import JsonEventEmitter
e = JsonEventEmitter(enabled=True)
e.emit("phase-started", phase="01a", workers=2, max_concurrent=4, force=True)
`;
    const stdout = runViaUv(harness);
    const warns: string[] = [];
    const ev = parsePipelineEvent(stdout.trim(), (f) => warns.push(f.reason));
    expect(warns).toEqual([]);
    expect(ev?.type).toBe("phase-started");
    if (ev?.type === "phase-started") {
      expect(ev.workers).toBe(2);
      expect(ev.max_concurrent).toBe(4);
      expect(ev.force).toBe(true);
    }
  }, 30_000);
});
