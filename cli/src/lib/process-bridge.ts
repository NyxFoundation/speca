/**
 * Process bridge — spawn `uv run python3 scripts/run_phase.py --json`
 * and stream typed pipeline events back to the caller.
 *
 * Spec ref: Issue #3 M3, SPECA_CLI_SPEC §9.
 */
import { spawn, type ChildProcess } from "node:child_process";
import { EventEmitter } from "node:events";
import { parseEventLine, type PipelineEvent } from "./events.js";

export interface BridgeOptions {
  /** Phases to run (e.g. ["01a", "01b"]) */
  phases?: string[];
  /** Target phase — resolve the full dependency chain */
  target?: string;
  /** Number of parallel workers */
  workers?: number;
  /** Max concurrent tasks per worker */
  maxConcurrent?: number;
  /** Force re-execution (bypass resume) */
  force?: boolean;
  /** Working directory (project root). Defaults to cwd. */
  cwd?: string;
}

export interface ProcessBridge {
  /** The underlying child process */
  child: ChildProcess;
  /** Event emitter for typed pipeline events */
  events: EventEmitter;
  /** Promise that resolves with exit code when process exits */
  exitPromise: Promise<number>;
  /** Send SIGTERM to the child process */
  stop(): void;
}

/**
 * Build the command-line arguments for `run_phase.py --json`.
 */
function buildArgs(opts: BridgeOptions): string[] {
  const args = ["run", "python3", "scripts/run_phase.py", "--json"];

  if (opts.target) {
    args.push("--target", opts.target);
  } else if (opts.phases && opts.phases.length > 0) {
    args.push("--phase", ...opts.phases);
  }

  if (opts.workers !== undefined) {
    args.push("--workers", String(opts.workers));
  }
  if (opts.maxConcurrent !== undefined) {
    args.push("--max-concurrent", String(opts.maxConcurrent));
  }
  if (opts.force) {
    args.push("--force");
  }

  return args;
}

/**
 * Spawn the orchestrator process and return a bridge for consuming events.
 *
 * Events are emitted on the returned `events` emitter as:
 *   - "event"  (PipelineEvent)     — typed pipeline event
 *   - "stderr" (string)            — raw stderr line (for log pane)
 *   - "error"  (Error)             — spawn failure
 *   - "exit"   (number)            — process exit code
 */
export function spawnPipeline(opts: BridgeOptions = {}): ProcessBridge {
  const cwd = opts.cwd ?? process.cwd();
  const args = buildArgs(opts);
  const events = new EventEmitter();

  const child = spawn("uv", args, {
    cwd,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env },
  });

  let stdoutBuffer = "";
  let stderrBuffer = "";

  child.stdout?.on("data", (chunk: Buffer) => {
    stdoutBuffer += chunk.toString("utf8");
    const lines = stdoutBuffer.split("\n");
    // Keep incomplete last line in buffer
    stdoutBuffer = lines.pop() ?? "";
    for (const line of lines) {
      const event = parseEventLine(line);
      if (event) {
        events.emit("event", event);
      }
    }
  });

  child.stderr?.on("data", (chunk: Buffer) => {
    stderrBuffer += chunk.toString("utf8");
    const lines = stderrBuffer.split("\n");
    stderrBuffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.trim()) {
        events.emit("stderr", line);
      }
    }
  });

  const exitPromise = new Promise<number>((resolve) => {
    child.on("error", (err) => {
      events.emit("error", err);
      resolve(1);
    });
    child.on("close", (code) => {
      // Flush remaining buffers
      if (stdoutBuffer.trim()) {
        const event = parseEventLine(stdoutBuffer);
        if (event) events.emit("event", event);
      }
      if (stderrBuffer.trim()) {
        events.emit("stderr", stderrBuffer);
      }
      const exitCode = code ?? 1;
      events.emit("exit", exitCode);
      resolve(exitCode);
    });
  });

  return {
    child,
    events,
    exitPromise,
    stop() {
      if (!child.killed) {
        child.kill("SIGTERM");
      }
    },
  };
}
