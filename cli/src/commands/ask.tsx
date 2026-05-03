/**
 * `speca ask` — chat with Claude about a SPECA finding (M5).
 *
 * Spec reference: docs/SPECA_CLI_SPEC.md §5.5 / §8.5.
 *
 * CLI surface:
 *
 *   $ speca ask                                     # chat without finding context
 *   $ speca ask <finding-id>                        # chat about a specific finding
 *   $ speca ask --from outputs/04_PARTIAL.json      # load finding from a file
 *   $ speca ask --session abc123ef-...              # resume a specific session
 *   $ speca ask --max-context 30000                 # tighten context cap (bytes)
 *   $ speca ask --no-tui                            # reserved for M6
 *
 * Findings are looked up by `property_id` (preferred) or `checklist_id`
 * inside the file passed via --from. The file may be:
 *   - a Phase 03/04 partial JSON (with `audit_items[]` or `reviewed_items[]`)
 *   - a single finding object
 *   - an array of finding objects
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render } from "ink";
import { createElement } from "react";

import { AskChat } from "../components/AskChat.js";
import { composeAskPrompt, type FindingContextInput } from "../lib/claude-session/context.js";
import { spawnAsk, type ParsedEvent } from "../lib/claude-session/spawn.js";
import { loadSession, saveSession, newSessionInfo, touchSessionInfo } from "../lib/claude-session/store.js";

export interface AskCommandFlags {
  from?: string;
  session?: string;
  maxContext?: number;
  noTui?: boolean;
}

export interface AskCommandOptions {
  positional: string[];
  flags: AskCommandFlags;
  /** Override stdout for tests. */
  log?: (msg: string) => void;
  errorLog?: (msg: string) => void;
  /** Override the spawn implementation for tests. */
  spawnFn?: typeof spawnAsk;
  /** Override the project root for tests. */
  projectRoot?: string;
}

const HELP_TEXT = `\
speca ask — chat with Claude about a SPECA finding

Usage
  $ speca ask [finding-id] [flags]

Arguments
  finding-id              Look up this property_id / checklist_id in --from

Flags
  --from <file>           Path to a Phase 03/04 PARTIAL JSON or finding file
  --session <id>          Resume an existing Claude Code session id
  --max-context <bytes>   Cap the injected finding context (default 50000 = 50 KB)
  --no-tui                Headless mode: reads question from stdin, prints
                          assistant text to stdout (single turn). M6 may
                          extend this further.

Examples
  $ speca ask
  $ speca ask PROP-abc-001 --from outputs/04_PARTIAL_*.json
  $ speca ask --session 9f1c2e0a-...
  $ speca ask --no-tui --from finding.json --max-context 10000
`;

export function printAskHelp(): void {
  process.stdout.write(HELP_TEXT);
}

interface ResolvedFinding {
  finding: FindingContextInput;
  label: string;
}

/**
 * Try to find a single finding object inside an arbitrary JSON file.
 *
 * Accepts:
 *   - a raw finding object with `property_id` (or `checklist_id`)
 *   - an array of findings — the first one whose id matches `findingId` wins,
 *     or the first overall when `findingId` is omitted
 *   - a Phase 03 partial: { audit_items: [...] }
 *   - a Phase 04 partial: { reviewed_items: [...] }
 */
export function pickFinding(
  raw: unknown,
  findingId?: string,
): ResolvedFinding | null {
  const candidates: FindingContextInput[] = [];
  if (Array.isArray(raw)) {
    for (const item of raw) if (item && typeof item === "object") candidates.push(item as FindingContextInput);
  } else if (raw && typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    if (Array.isArray(obj.audit_items)) {
      for (const item of obj.audit_items) {
        if (item && typeof item === "object") candidates.push(item as FindingContextInput);
      }
    }
    if (Array.isArray(obj.reviewed_items)) {
      for (const item of obj.reviewed_items) {
        if (item && typeof item === "object") {
          const ri = item as Record<string, unknown>;
          // Phase 04 wraps the original under `original_finding`; lift core
          // fields so context.ts sees them directly.
          if (ri.original_finding && typeof ri.original_finding === "object") {
            const merged: FindingContextInput = {
              ...(ri.original_finding as Record<string, unknown>),
              ...(typeof ri.verdict === "string" ? { verdict: ri.verdict } : {}),
            };
            candidates.push(merged);
          } else {
            candidates.push(ri as FindingContextInput);
          }
        }
      }
    }
    if (candidates.length === 0) {
      // Treat as a single finding
      candidates.push(obj as FindingContextInput);
    }
  }

  if (candidates.length === 0) return null;

  let chosen: FindingContextInput | undefined;
  if (findingId) {
    chosen = candidates.find((f) => {
      const a = typeof f.property_id === "string" ? f.property_id : "";
      const b = typeof f.checklist_id === "string" ? f.checklist_id : "";
      return a === findingId || b === findingId;
    });
  }
  if (!chosen) chosen = candidates[0];
  if (!chosen) return null;

  const id =
    (typeof chosen.property_id === "string" && chosen.property_id) ||
    (typeof chosen.checklist_id === "string" && chosen.checklist_id) ||
    "(unknown)";
  const sev = typeof chosen.severity === "string" ? ` (${chosen.severity})` : "";
  return { finding: chosen, label: `${id}${sev}` };
}

function loadFindingFromFile(path: string): ResolvedFinding | null {
  const abs = resolve(path);
  const raw = readFileSync(abs, "utf8");
  const parsed = JSON.parse(raw) as unknown;
  return pickFinding(parsed);
}

export async function runAskCommand(opts: AskCommandOptions): Promise<number> {
  const log = opts.log ?? ((m: string) => process.stdout.write(`${m}\n`));
  const errorLog = opts.errorLog ?? ((m: string) => process.stderr.write(`${m}\n`));

  const findingId = opts.positional[0];
  let resolved: ResolvedFinding | null = null;
  if (opts.flags.from) {
    try {
      resolved = loadFindingFromFile(opts.flags.from);
    } catch (err) {
      errorLog(`speca ask: failed to read --from ${opts.flags.from}: ${(err as Error).message}`);
      return 2;
    }
    if (!resolved) {
      errorLog(`speca ask: no finding found inside ${opts.flags.from}`);
      return 2;
    }
    if (findingId) {
      // Try to refine with the explicit id.
      try {
        const raw = JSON.parse(readFileSync(resolve(opts.flags.from), "utf8")) as unknown;
        const refined = pickFinding(raw, findingId);
        if (refined) resolved = refined;
      } catch {
        // Already validated above; ignore.
      }
    }
  } else if (findingId) {
    errorLog(
      `speca ask: bare finding-id is not yet wired to project lookup. Pass --from <file> to load it.`,
    );
    return 2;
  }

  // Reserved-flag pass-through path used by M6 / scripts.
  if (opts.flags.noTui) {
    return runAskNonTui({
      finding: resolved?.finding ?? null,
      sessionId: opts.flags.session,
      maxContextBytes: opts.flags.maxContext,
      projectRoot: opts.projectRoot,
      spawnFn: opts.spawnFn,
      log,
      errorLog,
    });
  }

  const app = render(
    createElement(AskChat, {
      finding: resolved?.finding ?? null,
      findingLabel: resolved?.label,
      initialSessionId: opts.flags.session,
      maxContextBytes: opts.flags.maxContext,
      projectRoot: opts.projectRoot,
      spawnFn: opts.spawnFn,
    }),
  );
  try {
    await app.waitUntilExit();
    return 0;
  } catch (err) {
    errorLog(`speca ask: ${(err as Error).message}`);
    return 1;
  }
}

interface NonTuiArgs {
  finding: FindingContextInput | null;
  sessionId?: string;
  maxContextBytes?: number;
  projectRoot?: string;
  spawnFn?: typeof spawnAsk;
  log: (msg: string) => void;
  errorLog: (msg: string) => void;
}

/**
 * Stream a single turn to stdout without launching Ink. Used by `--no-tui`
 * (the proper M6 surface will probably be richer, but this lets scripts and
 * tests drive the pipeline today). Reads the question from stdin.
 */
async function runAskNonTui(args: NonTuiArgs): Promise<number> {
  const spawnImpl = args.spawnFn ?? spawnAsk;

  // Read the question. If stdin is a TTY there's no piped question → just emit
  // the spec'd help and exit (we're not going to prompt in headless mode).
  let question = "";
  if (process.stdin.isTTY) {
    args.errorLog("speca ask --no-tui: pipe a question on stdin (e.g. `echo Q | speca ask --no-tui`).");
    return 2;
  }
  for await (const chunk of process.stdin) {
    question += typeof chunk === "string" ? chunk : (chunk as Buffer).toString("utf8");
  }
  question = question.trim();
  if (question.length === 0) {
    args.errorLog("speca ask --no-tui: empty question on stdin.");
    return 2;
  }

  const root = args.projectRoot ?? process.cwd();
  const existing = await loadSession(root);
  let sid = args.sessionId ?? existing?.session_id;
  const isFirstTurn = !sid;
  const composed = composeAskPrompt(isFirstTurn ? args.finding : null, question, {
    maxBytes: args.maxContextBytes,
  });

  let handle;
  try {
    handle = await spawnImpl({ prompt: composed.prompt, sessionId: sid });
  } catch (err) {
    args.errorLog(`speca ask: ${(err as Error).message}`);
    return 1;
  }

  let learnedSid: string | undefined = sid;
  let exitCode = 0;
  for await (const ev of handle.events as AsyncIterable<ParsedEvent>) {
    if (ev.type === "assistant" && ev.text.length > 0) {
      args.log(ev.text);
    }
    if ((ev.type === "system" || ev.type === "assistant" || ev.type === "result") && ev.session_id) {
      learnedSid = ev.session_id;
    }
    if (ev.type === "stderr") {
      args.errorLog(`[claude stderr] ${ev.line}`);
    }
    if (ev.type === "spawn-error") {
      args.errorLog(`[spawn-error] ${ev.message}`);
      exitCode = 1;
    }
    if (ev.type === "done") {
      if (typeof ev.code === "number" && ev.code !== 0) exitCode = ev.code;
      break;
    }
  }

  if (learnedSid) {
    try {
      const info = existing
        ? touchSessionInfo({ ...existing, session_id: learnedSid }, composed.context?.bytes ?? 0)
        : newSessionInfo(learnedSid, composed.context?.bytes ?? 0);
      await saveSession(info, root);
    } catch {
      // ignore
    }
  }

  return exitCode;
}
