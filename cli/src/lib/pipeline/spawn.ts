/**
 * Process bridge for `uv run python3 scripts/run_phase.py --json`.
 *
 * Responsibilities:
 *   - Spawn the orchestrator subprocess (no PTY — stdout pipe is sufficient
 *     because run_phase.py is non-interactive).
 *   - Read stdout line-by-line, NDJSON-parse each line into a PipelineEvent.
 *   - Forward stderr (decorative output + tracebacks) verbatim to a callback.
 *   - Surface child exit code + stop signal (SIGTERM / SIGKILL) via callbacks.
 *
 * Per SPEC §9.3 #2 (node-pty has no prebuilt binaries) we default to plain
 * `child_process.spawn`. node-pty is only needed when wrapping the embedded
 * `claude` chat session (M5), so M3 stays toolchain-light.
 */
import { type ChildProcessByStdio, spawn } from "node:child_process";
import type { Readable } from "node:stream";
import { EventEmitter } from "node:events";
import { parsePipelineEvent, splitLines, type ParseFailure, type PipelineEvent } from "./events.js";

export interface SpawnPipelineOptions {
  /** Phases to run (mutually exclusive with `target`). */
  phases?: string[];
  /** Target phase — runs full dependency chain. */
  target?: string;
  /** Worker count (default 4). */
  workers?: number;
  /** Max concurrent Claude executions (default 8). */
  maxConcurrent?: number;
  /** Pass `--force` to clear resume state. */
  force?: boolean;
  /** Override SPECA_OUTPUT_DIR. */
  outputDir?: string;
  /** Working directory (defaults to process.cwd()). */
  cwd?: string;
  /** Emit additional `--budget` argument when defined. (Reserved.) */
  budget?: number;
  /** Allow swapping the runner for tests; defaults to `uv`. */
  command?: string;
  /** Allow custom argv prefix for tests; defaults to ['run','python3','scripts/run_phase.py']. */
  baseArgs?: string[];
  /** Inherit env from parent. */
  env?: NodeJS.ProcessEnv;
}

export interface PipelineRunHandle extends EventEmitter {
  /** Send SIGTERM (graceful). Returns true if the signal was delivered. */
  stop(): boolean;
  /** Send SIGKILL (force). */
  kill(): boolean;
  /** Resolves when the child exits, with the final exit code. */
  done: Promise<number>;
  /** Underlying pid (or undefined if spawn failed). */
  readonly pid: number | undefined;
}

export type PipelineRunEvent =
  | { kind: "event"; event: PipelineEvent }
  | { kind: "warn"; failure: ParseFailure }
  | { kind: "stderr"; line: string }
  | { kind: "exit"; code: number; signal: NodeJS.Signals | null }
  | { kind: "spawn-error"; error: Error };

export interface PipelineRunHandleTyped extends PipelineRunHandle {
  on(event: "event", listener: (e: PipelineEvent) => void): this;
  on(event: "warn", listener: (f: ParseFailure) => void): this;
  on(event: "stderr", listener: (line: string) => void): this;
  on(event: "exit", listener: (code: number, signal: NodeJS.Signals | null) => void): this;
  on(event: "spawn-error", listener: (err: Error) => void): this;
  emit(event: "event", e: PipelineEvent): boolean;
  emit(event: "warn", f: ParseFailure): boolean;
  emit(event: "stderr", line: string): boolean;
  emit(event: "exit", code: number, signal: NodeJS.Signals | null): boolean;
  emit(event: "spawn-error", err: Error): boolean;
}

function buildArgs(opts: SpawnPipelineOptions): string[] {
  const args: string[] = [];
  if (opts.target) {
    args.push("--target", opts.target);
  } else if (opts.phases && opts.phases.length > 0) {
    args.push("--phase", ...opts.phases);
  } else {
    throw new Error("spawnPipeline: either `phases` or `target` must be provided");
  }
  if (opts.workers !== undefined) args.push("--workers", String(opts.workers));
  if (opts.maxConcurrent !== undefined) args.push("--max-concurrent", String(opts.maxConcurrent));
  if (opts.force) args.push("--force");
  if (opts.outputDir) args.push("--output-dir", opts.outputDir);
  args.push("--json");
  return args;
}

const KILL_GRACE_MS = 5_000;

export function spawnPipeline(opts: SpawnPipelineOptions): PipelineRunHandleTyped {
  const command = opts.command ?? "uv";
  const baseArgs = opts.baseArgs ?? ["run", "python3", "scripts/run_phase.py"];
  const args = [...baseArgs, ...buildArgs(opts)];

  const emitter = new EventEmitter() as PipelineRunHandleTyped;

  let child: ChildProcessByStdio<null, Readable, Readable> | null = null;
  let killTimer: NodeJS.Timeout | null = null;
  let resolveDone: (code: number) => void = () => {};
  const done = new Promise<number>((resolve) => {
    resolveDone = resolve;
  });

  Object.defineProperty(emitter, "done", { value: done });
  Object.defineProperty(emitter, "pid", {
    get(): number | undefined {
      return child?.pid;
    },
  });

  emitter.stop = () => {
    if (!child || child.exitCode !== null) return false;
    const ok = child.kill("SIGTERM");
    // Auto-escalate to SIGKILL if the child does not exit within the grace window.
    if (ok) {
      killTimer = setTimeout(() => {
        if (child && child.exitCode === null) {
          try {
            child.kill("SIGKILL");
          } catch {
            // already gone
          }
        }
      }, KILL_GRACE_MS);
      // Don't keep the event loop alive just for the timer.
      killTimer.unref?.();
    }
    return ok;
  };
  emitter.kill = () => {
    if (!child || child.exitCode !== null) return false;
    if (killTimer) {
      clearTimeout(killTimer);
      killTimer = null;
    }
    return child.kill("SIGKILL");
  };

  try {
    child = spawn(command, args, {
      cwd: opts.cwd,
      env: { ...process.env, ...(opts.env ?? {}) },
      stdio: ["ignore", "pipe", "pipe"],
      // On Windows, `uv` is typically `uv.exe`. Node resolves it without
      // the shell when PATHEXT includes .exe; we avoid `shell: true` to
      // keep argv quoting predictable.
      windowsHide: true,
    });
  } catch (err) {
    setImmediate(() => {
      emitter.emit("spawn-error", err as Error);
      emitter.emit("exit", 127, null);
      resolveDone(127);
    });
    return emitter;
  }

  // Defensive: on platforms without spawn errors thrown synchronously,
  // child can still be null if spawn returned without a process.
  const c = child as ChildProcessByStdio<null, Readable, Readable>;

  let stdoutCarry = "";
  let stderrCarry = "";
  c.stdout.setEncoding("utf8");
  c.stderr.setEncoding("utf8");

  c.stdout.on("data", (chunk: string) => {
    const { lines, carry } = splitLines(chunk, stdoutCarry);
    stdoutCarry = carry;
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed === "") continue;
      const event = parsePipelineEvent(trimmed, (failure) => emitter.emit("warn", failure));
      if (event) emitter.emit("event", event);
    }
  });

  c.stderr.on("data", (chunk: string) => {
    const { lines, carry } = splitLines(chunk, stderrCarry);
    stderrCarry = carry;
    for (const line of lines) {
      emitter.emit("stderr", line);
    }
  });

  c.on("error", (err) => {
    emitter.emit("spawn-error", err);
  });

  c.on("close", (code, signal) => {
    if (killTimer) {
      clearTimeout(killTimer);
      killTimer = null;
    }
    // Flush any remaining partial line.
    if (stdoutCarry.trim() !== "") {
      const event = parsePipelineEvent(stdoutCarry, (failure) => emitter.emit("warn", failure));
      if (event) emitter.emit("event", event);
      stdoutCarry = "";
    }
    if (stderrCarry.trim() !== "") {
      emitter.emit("stderr", stderrCarry);
      stderrCarry = "";
    }
    const exitCode = code ?? (signal ? 128 : 0);
    emitter.emit("exit", exitCode, signal ?? null);
    resolveDone(exitCode);
  });

  return emitter;
}
