/**
 * Spawn `claude -p ... --output-format stream-json [--resume <session-id>]`
 * and return a typed event stream (M5 — `speca ask`).
 *
 * Spec reference: docs/SPECA_CLI_SPEC.md §8.5 "Ask Claude implementation".
 *
 * Design notes:
 *   - Prompt is always piped via stdin. claude CLI accepts `--input-format
 *     text -p` (no positional) which makes it read stdin verbatim. This is
 *     mandatory on Windows because the `claude.cmd` shim goes through
 *     `cmd.exe`, which mangles markdown metacharacters in argv (& | ^ > < (
 *     ) % ! and embedded newlines). Same pattern as PR #4 in the Python
 *     orchestrator.
 *   - Resolve `claude.cmd` first on Windows so we hit the npm-shim instead of
 *     a missing `claude` symlink.
 *   - stream-json output is one JSON object per line. We emit "assistant" /
 *     "result" events plus a final "done" or "error" — see ParsedEvent.
 *   - stderr is piped back as "stderr" events (the CLI prints diagnostic
 *     lines there).
 *   - `inheritEnv: true` (per spec) so the parent shell's Claude Code
 *     subscription credentials reach the subprocess unchanged.
 */

import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { platform } from "node:os";
import which from "which";

export type ParsedEvent =
  | { type: "system"; subtype?: string; session_id?: string; raw: unknown }
  | { type: "assistant"; text: string; session_id?: string; raw: unknown }
  | { type: "user"; text: string; session_id?: string; raw: unknown }
  | { type: "result"; subtype?: string; session_id?: string; raw: unknown }
  | { type: "stderr"; line: string }
  | { type: "stream-error"; line: string; error: string }
  | { type: "done"; code: number | null; session_id?: string }
  | { type: "spawn-error"; message: string };

export interface SpawnAskOptions {
  /** UTF-8 prompt to feed claude on stdin. Required. */
  prompt: string;
  /** Resume an existing Claude Code session (omit for a brand-new session). */
  sessionId?: string;
  /** Override the resolved claude binary (mostly for tests). */
  claudeBin?: string;
  /**
   * Extra positional args inserted BEFORE the claude flag block. Used by
   * tests to wedge a fake script path between the binary and the flags
   * (e.g. `node fake-claude.mjs -p --output-format ...`). Production callers
   * should never need this.
   */
  extraArgs?: string[];
  /** Working directory for the subprocess (default: process.cwd()). */
  cwd?: string;
  /** Custom env. Defaults to inheriting the parent process env. */
  env?: NodeJS.ProcessEnv;
  /**
   * AbortSignal — when aborted, sends SIGTERM to the child. Lets the chat UI
   * cancel a long generation when the user presses Esc.
   */
  signal?: AbortSignal;
}

export interface SpawnAskHandle {
  /** Async iterable of parsed events. Consume in a `for await` loop. */
  events: AsyncIterable<ParsedEvent>;
  /** PID of the spawned child (undefined if spawn failed synchronously). */
  pid?: number;
  /** Manual kill (in addition to AbortSignal). */
  kill(): void;
}

/**
 * Resolve the `claude` executable path. On Windows we prefer `claude.cmd`
 * (the npm-installed shim) and fall back to bare `claude` only if the shim is
 * not present. On POSIX we just use the binary on PATH. Returns null when
 * nothing is found.
 *
 * Public so `cli/src/lib/checks.ts` and tests can introspect the resolution
 * without re-implementing the search.
 */
export async function resolveClaudeBin(): Promise<string | null> {
  if (platform() === "win32") {
    const cmd = await which("claude.cmd", { nothrow: true });
    if (cmd) return cmd;
  }
  return which("claude", { nothrow: true });
}

/**
 * Parse one stream-json line into a ParsedEvent. Exported for the unit test.
 *
 * Stream-json shape (informal, matches `claude --output-format stream-json`):
 *   { "type": "system", "subtype": "init", "session_id": "...", ... }
 *   { "type": "assistant", "message": { "content": [{type:"text", text:"..."}]}, ... }
 *   { "type": "user",      "message": { "content": [{type:"text", text:"..."}]}, ... }
 *   { "type": "result",    "subtype": "success", "session_id": "...", ... }
 */
export function parseStreamJsonLine(line: string): ParsedEvent | null {
  const trimmed = line.trim();
  if (trimmed.length === 0) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch (err) {
    return { type: "stream-error", line: trimmed, error: (err as Error).message };
  }
  if (!parsed || typeof parsed !== "object") {
    return { type: "stream-error", line: trimmed, error: "non-object stream-json line" };
  }
  const obj = parsed as Record<string, unknown>;
  const sessionId = typeof obj.session_id === "string" ? obj.session_id : undefined;
  const t = typeof obj.type === "string" ? obj.type : "";
  if (t === "assistant" || t === "user") {
    return {
      type: t,
      text: extractText(obj.message),
      session_id: sessionId,
      raw: obj,
    };
  }
  if (t === "system") {
    return {
      type: "system",
      subtype: typeof obj.subtype === "string" ? obj.subtype : undefined,
      session_id: sessionId,
      raw: obj,
    };
  }
  if (t === "result") {
    return {
      type: "result",
      subtype: typeof obj.subtype === "string" ? obj.subtype : undefined,
      session_id: sessionId,
      raw: obj,
    };
  }
  // Pass unknown event types through as system-shaped fallback so the UI can
  // surface them as "(unknown event)" without exploding.
  return { type: "system", subtype: t || undefined, session_id: sessionId, raw: obj };
}

function extractText(message: unknown): string {
  // Claude's stream-json wraps text in `message.content[]` where each item is
  // `{ type: "text", text: "..." }` (other types: tool_use, tool_result, ...).
  if (!message || typeof message !== "object") return "";
  const m = message as { content?: unknown };
  if (Array.isArray(m.content)) {
    const out: string[] = [];
    for (const item of m.content) {
      if (item && typeof item === "object") {
        const it = item as { type?: string; text?: unknown };
        if (it.type === "text" && typeof it.text === "string") {
          out.push(it.text);
        }
      }
    }
    return out.join("");
  }
  if (typeof m.content === "string") return m.content;
  return "";
}

/**
 * Build the argv that gets passed to claude. Pure helper, exported for the
 * unit test so we can pin the exact flag layout the spec requires.
 */
export function buildClaudeArgs(sessionId: string | undefined, extra: string[] = []): string[] {
  // Extras go FIRST so a test can wedge a fake script between `node` and the
  // claude flag block. Production callers leave `extra` empty.
  const args: string[] = [...extra];
  args.push(
    "-p",
    "--input-format",
    "text",
    "--output-format",
    "stream-json",
    "--verbose", // claude CLI requires --verbose to enable stream-json with -p
  );
  if (sessionId) {
    args.push("--resume", sessionId);
  }
  return args;
}

class SpawnError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SpawnError";
  }
}

/**
 * Spawn the claude subprocess and return an event-stream handle. The async
 * iterable yields parsed events as they arrive on stdout; "stderr" events for
 * lines from stderr; a single "done" event when the child exits cleanly; and
 * a single "spawn-error" event if the child cannot be launched at all.
 */
export async function spawnAsk(options: SpawnAskOptions): Promise<SpawnAskHandle> {
  const bin = options.claudeBin ?? (await resolveClaudeBin());
  if (!bin) {
    throw new SpawnError(
      "claude CLI not found on PATH. Install via `npm install -g @anthropic-ai/claude-code`.",
    );
  }
  const args = buildClaudeArgs(options.sessionId, options.extraArgs);

  // On Windows, .cmd shims must be invoked via cmd.exe explicitly under
  // Node 22.5+ (CVE-2024-27980 / DEP0190). Same pattern as cli/src/lib/checks.ts.
  const isWinScript = platform() === "win32" && /\.(cmd|bat)$/i.test(bin);
  const execPath = isWinScript ? "cmd.exe" : bin;
  const execArgs = isWinScript ? ["/d", "/s", "/c", bin, ...args] : args;

  let child: ChildProcessWithoutNullStreams;
  try {
    child = spawn(execPath, execArgs, {
      cwd: options.cwd ?? process.cwd(),
      env: options.env ?? process.env,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    }) as ChildProcessWithoutNullStreams;
  } catch (err) {
    throw new SpawnError(`failed to spawn claude: ${(err as Error).message}`);
  }

  // Hook abort.
  if (options.signal) {
    if (options.signal.aborted) {
      child.kill("SIGTERM");
    } else {
      options.signal.addEventListener(
        "abort",
        () => {
          if (!child.killed) child.kill("SIGTERM");
        },
        { once: true },
      );
    }
  }

  // Pipe the prompt in, then close stdin so claude proceeds.
  if (child.stdin) {
    try {
      child.stdin.end(options.prompt, "utf8");
    } catch (err) {
      // EPIPE happens if claude died before we could write. The events
      // generator below will surface the spawn failure as "done" with the
      // child's exit code.
      void err;
    }
  }

  const events = createEventStream(child);

  return {
    events,
    pid: child.pid,
    kill() {
      if (!child.killed) child.kill("SIGTERM");
    },
  };
}

function createEventStream(child: ChildProcessWithoutNullStreams): AsyncIterable<ParsedEvent> {
  return {
    [Symbol.asyncIterator]() {
      const queue: ParsedEvent[] = [];
      let waiter: ((e: IteratorResult<ParsedEvent>) => void) | null = null;
      let finished = false;
      let errored: Error | null = null;
      let lastSessionId: string | undefined;

      const push = (e: ParsedEvent): void => {
        if (
          (e.type === "assistant" || e.type === "system" || e.type === "result") &&
          e.session_id
        ) {
          lastSessionId = e.session_id;
        }
        if (waiter) {
          const w = waiter;
          waiter = null;
          w({ value: e, done: false });
        } else {
          queue.push(e);
        }
      };

      const finish = (code: number | null): void => {
        if (finished) return;
        finished = true;
        push({ type: "done", code, session_id: lastSessionId });
        // Push a sentinel `done: true` next time the consumer asks.
        if (waiter) {
          const w = waiter;
          waiter = null;
          w({ value: undefined as unknown as ParsedEvent, done: true });
        }
      };

      // Line-buffered stdout reader.
      let stdoutBuf = "";
      child.stdout.setEncoding("utf8");
      child.stdout.on("data", (chunk: string) => {
        stdoutBuf += chunk;
        let nl: number;
        // biome-ignore lint/suspicious/noAssignInExpressions: simple split loop
        while ((nl = stdoutBuf.indexOf("\n")) !== -1) {
          const line = stdoutBuf.slice(0, nl);
          stdoutBuf = stdoutBuf.slice(nl + 1);
          const ev = parseStreamJsonLine(line);
          if (ev) push(ev);
        }
      });
      child.stdout.on("end", () => {
        if (stdoutBuf.length > 0) {
          const ev = parseStreamJsonLine(stdoutBuf);
          stdoutBuf = "";
          if (ev) push(ev);
        }
      });

      // Line-buffered stderr reader (one event per line).
      let stderrBuf = "";
      child.stderr.setEncoding("utf8");
      child.stderr.on("data", (chunk: string) => {
        stderrBuf += chunk;
        let nl: number;
        // biome-ignore lint/suspicious/noAssignInExpressions: simple split loop
        while ((nl = stderrBuf.indexOf("\n")) !== -1) {
          const line = stderrBuf.slice(0, nl);
          stderrBuf = stderrBuf.slice(nl + 1);
          if (line.length > 0) push({ type: "stderr", line });
        }
      });
      child.stderr.on("end", () => {
        if (stderrBuf.length > 0) {
          push({ type: "stderr", line: stderrBuf });
          stderrBuf = "";
        }
      });

      child.on("error", (err) => {
        errored = err;
        push({ type: "spawn-error", message: err.message });
      });
      child.on("close", (code) => {
        finish(code);
      });

      return {
        next(): Promise<IteratorResult<ParsedEvent>> {
          if (queue.length > 0) {
            const value = queue.shift() as ParsedEvent;
            return Promise.resolve({ value, done: false });
          }
          if (finished) {
            return Promise.resolve({ value: undefined as unknown as ParsedEvent, done: true });
          }
          if (errored) {
            const e = errored;
            errored = null;
            return Promise.reject(e);
          }
          return new Promise((resolve) => {
            waiter = resolve;
          });
        },
        return(): Promise<IteratorResult<ParsedEvent>> {
          if (!child.killed) child.kill("SIGTERM");
          finish(child.exitCode ?? null);
          return Promise.resolve({ value: undefined as unknown as ParsedEvent, done: true });
        },
      };
    },
  };
}
