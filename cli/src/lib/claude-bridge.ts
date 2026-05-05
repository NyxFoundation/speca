/**
 * Claude Code chat bridge for the "Ask Claude" pane (M5).
 *
 * Spawns `claude -p <prompt> --output-format stream-json --resume <session-id>`
 * and streams tokens back to the caller.
 *
 * Spec ref: Issue #3 M5, SPECA_CLI_SPEC §8.5.
 */
import { spawn, type ChildProcess } from "node:child_process";
import { promises as fs } from "node:fs";
import { resolve, dirname } from "node:path";
import { EventEmitter } from "node:events";

const MAX_CONTEXT_BYTES = 50 * 1024; // 50 KB cap per §8.5

export interface SessionInfo {
  sessionId: string;
  projectDir: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ClaudeChatBridge {
  events: EventEmitter;
  child: ChildProcess;
  exitPromise: Promise<number>;
  stop(): void;
}

/**
 * Load or create session info from .speca/session.json.
 */
export async function loadSession(projectDir: string): Promise<SessionInfo> {
  const sessionFile = resolve(projectDir, ".speca", "session.json");
  try {
    const raw = JSON.parse(await fs.readFile(sessionFile, "utf8"));
    if (raw.sessionId && typeof raw.sessionId === "string") {
      return { sessionId: raw.sessionId, projectDir };
    }
  } catch {
    // file doesn't exist or is malformed
  }
  // No existing session — Claude will create one
  return { sessionId: "", projectDir };
}

/**
 * Save session info after receiving a session ID from Claude.
 */
export async function saveSession(info: SessionInfo): Promise<void> {
  const sessionFile = resolve(info.projectDir, ".speca", "session.json");
  await fs.mkdir(dirname(sessionFile), { recursive: true });
  await fs.writeFile(sessionFile, JSON.stringify({ sessionId: info.sessionId }, null, 2) + "\n", "utf8");
}

/**
 * Build the system context from a finding, respecting the 50KB cap.
 */
export function buildFindingContext(finding: {
  propertyId: string;
  classification: string;
  severity: string;
  verdict: string;
  summary: string;
  reviewerNotes: string;
  codePath: string;
  codeSnippet: string;
}): string {
  const parts = [
    `## Finding: ${finding.propertyId}`,
    `Classification: ${finding.classification}`,
    `Severity: ${finding.severity}`,
    `Verdict: ${finding.verdict}`,
    "",
    `### Summary`,
    finding.summary,
  ];

  if (finding.reviewerNotes) {
    parts.push("", "### Reviewer Notes", finding.reviewerNotes);
  }
  if (finding.codePath) {
    parts.push("", `### Code Location`, finding.codePath);
  }
  if (finding.codeSnippet) {
    parts.push("", "### Code / Proof Trace", "```", finding.codeSnippet, "```");
  }

  let context = parts.join("\n");
  if (Buffer.byteLength(context, "utf8") > MAX_CONTEXT_BYTES) {
    // Truncate to fit
    const buf = Buffer.from(context, "utf8");
    context = buf.subarray(0, MAX_CONTEXT_BYTES).toString("utf8");
    context += "\n\n[Context truncated to 50KB]";
  }
  return context;
}

/**
 * Stream-JSON event from Claude CLI output.
 * See: claude --output-format stream-json
 */
interface StreamJsonEvent {
  type: string;
  content_block?: { type: string; text?: string };
  delta?: { type: string; text?: string };
  message?: { id?: string };
  [key: string]: unknown;
}

/**
 * Spawn a Claude chat turn and stream tokens.
 *
 * Events emitted:
 *   "token"   (string)  — incremental text token
 *   "done"    (string)  — full response text
 *   "session" (string)  — session ID for --resume
 *   "error"   (Error)   — spawn or parse error
 */
export function askClaude(
  prompt: string,
  sessionId?: string,
  cwd?: string,
): ClaudeChatBridge {
  const args = ["-p", prompt, "--output-format", "stream-json"];
  if (sessionId) {
    args.push("--resume", sessionId);
  }

  const events = new EventEmitter();
  const child = spawn("claude", args, {
    cwd: cwd ?? process.cwd(),
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env },
  });

  let buffer = "";
  let fullText = "";

  child.stdout?.on("data", (chunk: Buffer) => {
    buffer += chunk.toString("utf8");
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.trim() || !line.startsWith("{")) continue;
      try {
        const evt = JSON.parse(line) as StreamJsonEvent;

        // Extract session ID from message_start
        if (evt.type === "message_start" && evt.message?.id) {
          events.emit("session", evt.message.id);
        }

        // Extract text tokens
        if (evt.type === "content_block_delta" && evt.delta?.text) {
          fullText += evt.delta.text;
          events.emit("token", evt.delta.text);
        }

        // Also handle result type from Claude CLI
        if (evt.type === "result" && typeof evt.result === "string") {
          fullText = evt.result as string;
        }
      } catch {
        // skip non-JSON lines
      }
    }
  });

  child.stderr?.on("data", () => {
    // Suppress stderr (claude CLI emits progress info there)
  });

  const exitPromise = new Promise<number>((resolve) => {
    child.on("error", (err) => {
      events.emit("error", err);
      resolve(1);
    });
    child.on("close", (code) => {
      // Flush buffer
      if (buffer.trim() && buffer.startsWith("{")) {
        try {
          const evt = JSON.parse(buffer) as StreamJsonEvent;
          if (evt.type === "result" && typeof evt.result === "string") {
            fullText = evt.result as string;
          }
        } catch {
          // ignore
        }
      }
      events.emit("done", fullText);
      resolve(code ?? 0);
    });
  });

  return {
    events,
    child,
    exitPromise,
    stop() {
      if (!child.killed) child.kill("SIGTERM");
    },
  };
}
