/**
 * Tail `outputs/logs/*.log.jsonl` files and parse Claude CLI stream-json
 * messages into typed log lines for the dashboard's log pane.
 *
 * Per SPEC §8.4 / §5.3.2:
 *   - One line per JSON object.
 *   - We extract the structural fields (type, subtype, tool name, message
 *     summary) and the worker/batch from the filename.
 *   - Unknown event types are surfaced via `onWarn` but never throw.
 *
 * Filename convention (see `scripts/orchestrator/runner.py`):
 *   `<phase_id>_w<worker>b<batch>_<ts>.log.jsonl`
 */
import { promises as fs } from "node:fs";
import { resolve, basename } from "node:path";
import chokidar, { type FSWatcher } from "chokidar";
import { z } from "zod";

export const logLineSchema = z.object({
  /** Phase id (e.g. "01a"). */
  phase: z.string(),
  /** Worker id parsed from filename (e.g. "0"). */
  worker: z.string(),
  /** Batch id parsed from filename (e.g. "3"). */
  batch: z.string(),
  /** ISO timestamp the event was observed (file mtime fallback). */
  ts: z.string(),
  /** Top-level Claude CLI stream-json type ("system" / "assistant" / etc.). */
  type: z.string(),
  /** Optional one-line human summary suitable for the log pane. */
  summary: z.string(),
  /** Severity for colour coding. */
  severity: z.enum(["info", "warn", "error"]),
  /** Tool name when this is a tool_use line, otherwise null. */
  tool: z.string().nullable(),
  /** Full source path of the originating log file. */
  sourcePath: z.string(),
});

export type LogLine = z.infer<typeof logLineSchema>;

/** Filename → {phase, worker, batch} parser. Returns null if the name does not fit. */
export function parseLogFilename(filename: string): { phase: string; worker: string; batch: string } | null {
  // {phase}_w{worker}b{batch}_{ts}.log.jsonl
  // Phase id can include alphanumerics; worker/batch are integers.
  const m = filename.match(/^([0-9a-zA-Z]+)_w(\d+)b(\d+)_.+\.log\.jsonl$/);
  if (!m) return null;
  return { phase: m[1] ?? "", worker: m[2] ?? "", batch: m[3] ?? "" };
}

interface RawClaudeBlock {
  type?: string;
  name?: string;
  text?: string;
  input?: unknown;
}

interface RawClaudeMessage {
  type?: string;
  subtype?: string;
  content?: RawClaudeBlock[] | string;
  model?: string;
  role?: string;
}

interface RawClaudeLine {
  type?: string;
  subtype?: string;
  message?: RawClaudeMessage;
  result?: unknown;
  is_error?: boolean;
  error?: { type?: string; message?: string } | string;
  usage?: { total_cost_usd?: number };
  total_cost_usd?: number;
}

/**
 * Convert a raw Claude stream-json line into a one-line summary for the
 * dashboard's log pane. Returns null if the line should be skipped.
 */
export function summariseRawLogLine(raw: unknown): { summary: string; severity: LogLine["severity"]; tool: string | null; type: string } | null {
  if (typeof raw !== "object" || raw === null) return null;
  const obj = raw as RawClaudeLine;
  const t = String(obj.type ?? "");
  if (t === "") return null;

  if (t === "error") {
    const err = obj.error;
    if (err && typeof err === "object") {
      return { summary: `error: ${err.type ?? ""} ${err.message ?? ""}`.trim(), severity: "error", tool: null, type: t };
    }
    return { summary: `error: ${typeof err === "string" ? err : "(unknown)"}`, severity: "error", tool: null, type: t };
  }

  if (t === "system") {
    const msg = obj.message ?? {};
    const sub = msg.subtype ?? "";
    const model = msg.model ? ` model=${msg.model}` : "";
    return { summary: `system: ${sub}${model}`.trim(), severity: "info", tool: null, type: t };
  }

  if (t === "assistant") {
    const msg = obj.message ?? {};
    const blocks = Array.isArray(msg.content) ? msg.content : [];
    for (const block of blocks) {
      if (block?.type === "tool_use") {
        const name = String(block.name ?? "tool");
        return { summary: `tool_use: ${name}`, severity: "info", tool: name, type: t };
      }
    }
    // Plain assistant text — use the first 80 chars to keep the row tight.
    const firstText = blocks.find((b) => b?.type === "text" && typeof b.text === "string");
    const text = firstText?.text ?? "";
    return { summary: text ? `assistant: ${truncate(text, 100)}` : "assistant: (empty)", severity: "info", tool: null, type: t };
  }

  if (t === "user") {
    const msg = obj.message ?? {};
    const blocks = Array.isArray(msg.content) ? msg.content : [];
    const tr = blocks.find((b) => b?.type === "tool_result");
    if (tr) return { summary: "tool_result", severity: "info", tool: null, type: t };
    return { summary: "user message", severity: "info", tool: null, type: t };
  }

  if (t === "result") {
    const isErr = Boolean(obj.is_error);
    const cost = obj.total_cost_usd ?? obj.usage?.total_cost_usd;
    const costStr = typeof cost === "number" ? ` cost=$${cost.toFixed(4)}` : "";
    return {
      summary: `result: ${isErr ? "error" : "ok"}${costStr}`,
      severity: isErr ? "error" : "info",
      tool: null,
      type: t,
    };
  }

  return { summary: t, severity: "info", tool: null, type: t };
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s.replace(/\s+/g, " ");
  return s.slice(0, n).replace(/\s+/g, " ") + "…";
}

export interface LogWatcherOptions {
  /** Directory to watch (typically `outputs/logs`). */
  dir: string;
  /** Called for each new line parsed. */
  onLine: (line: LogLine) => void;
  /** Called for malformed JSON / unknown shapes (warning only). */
  onWarn?: (msg: string) => void;
}

interface FileCursor {
  size: number;
  carry: string;
  meta: { phase: string; worker: string; batch: string } | null;
}

/**
 * Tail every `*.log.jsonl` under `dir` (recursive). Re-emits each new JSON
 * line as a structured `LogLine` via `onLine`.
 *
 * Returns a `close()` function that disposes the watcher.
 */
export async function startLogWatcher(opts: LogWatcherOptions): Promise<() => Promise<void>> {
  const { dir, onLine, onWarn } = opts;
  const cursors = new Map<string, FileCursor>();
  const absDir = resolve(dir);
  // Ensure dir exists so chokidar's `add` event fires consistently.
  try {
    await fs.mkdir(absDir, { recursive: true });
  } catch {
    // best-effort
  }

  const watcher: FSWatcher = chokidar.watch(`${absDir.replace(/\\/g, "/")}/**/*.log.jsonl`, {
    ignoreInitial: false,
    persistent: true,
    awaitWriteFinish: false,
  });

  async function readNewBytes(path: string): Promise<void> {
    let cursor = cursors.get(path);
    if (!cursor) {
      cursor = { size: 0, carry: "", meta: parseLogFilename(basename(path)) };
      cursors.set(path, cursor);
    }
    let stat: import("node:fs").Stats;
    try {
      stat = await fs.stat(path);
    } catch {
      return;
    }
    if (stat.size <= cursor.size) {
      // truncated or no growth
      if (stat.size < cursor.size) {
        cursor.size = 0;
        cursor.carry = "";
      }
      return;
    }
    const start = cursor.size;
    cursor.size = stat.size;
    let fh: import("node:fs/promises").FileHandle | null = null;
    try {
      fh = await fs.open(path, "r");
      const length = stat.size - start;
      const buf = Buffer.alloc(length);
      await fh.read(buf, 0, length, start);
      const chunk = cursor.carry + buf.toString("utf8");
      const parts = chunk.split(/\r?\n/);
      cursor.carry = parts.pop() ?? "";
      for (const part of parts) {
        const trimmed = part.trim();
        if (!trimmed) continue;
        let obj: unknown;
        try {
          obj = JSON.parse(trimmed);
        } catch {
          onWarn?.(`log-watcher: invalid JSON in ${basename(path)}`);
          continue;
        }
        const summary = summariseRawLogLine(obj);
        if (!summary) {
          onWarn?.(`log-watcher: unknown event in ${basename(path)}`);
          continue;
        }
        const meta = cursor.meta ?? { phase: "", worker: "", batch: "" };
        onLine({
          phase: meta.phase,
          worker: meta.worker,
          batch: meta.batch,
          ts: new Date(stat.mtimeMs).toISOString(),
          type: summary.type,
          summary: summary.summary,
          severity: summary.severity,
          tool: summary.tool,
          sourcePath: path,
        });
      }
    } finally {
      await fh?.close();
    }
  }

  watcher.on("add", (p) => {
    void readNewBytes(p);
  });
  watcher.on("change", (p) => {
    void readNewBytes(p);
  });

  return async () => {
    await watcher.close();
  };
}
