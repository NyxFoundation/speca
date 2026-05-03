/**
 * Per-project chat session store for `speca ask` (M5).
 *
 * Lives at `<projectRoot>/.speca/session.json` so each audit project gets its
 * own Claude Code session id. Intentionally NOT placed alongside the
 * user-level `auth.json` (see src/auth/store.ts) — that file holds secrets;
 * this file is project-local state and is fine to commit / .gitignore at the
 * project's discretion.
 *
 * Schema:
 *   {
 *     "session_id":              "abc123ef-...",
 *     "created_at":              1715678400123,
 *     "last_used_at":            1715679400999,
 *     "finding_context_bytes":   12345
 *   }
 *
 * On disk we tolerate (and pass through) extra keys so future fields added by
 * later milestones do not break older clients reading the file.
 */

import { promises as fs } from "node:fs";
import { dirname, join, resolve } from "node:path";

export interface SessionInfo {
  /** Claude Code session id (`--resume` argument). */
  session_id: string;
  /** Unix-ms timestamp this session was created (first save). */
  created_at: number;
  /** Unix-ms timestamp of the last `loadSession`/`touchSession`/`saveSession`. */
  last_used_at: number;
  /** Bytes of finding-context attached on the last turn (debug surface). */
  finding_context_bytes: number;
}

export interface SessionPaths {
  projectRoot: string;
  /** `<projectRoot>/.speca`. */
  dir: string;
  /** `<projectRoot>/.speca/session.json`. */
  file: string;
}

export const SESSION_DIR_NAME = ".speca";
export const SESSION_FILE_NAME = "session.json";

export function sessionPaths(projectRoot: string = process.cwd()): SessionPaths {
  const root = resolve(projectRoot);
  const dir = join(root, SESSION_DIR_NAME);
  return { projectRoot: root, dir, file: join(dir, SESSION_FILE_NAME) };
}

function isSessionInfo(value: unknown): value is SessionInfo {
  if (!value || typeof value !== "object") return false;
  const obj = value as Record<string, unknown>;
  if (typeof obj.session_id !== "string" || obj.session_id.length === 0) return false;
  if (typeof obj.created_at !== "number") return false;
  if (typeof obj.last_used_at !== "number") return false;
  if (typeof obj.finding_context_bytes !== "number") return false;
  return true;
}

/**
 * Read the session file. Returns null when the file does not exist or is
 * malformed — never throws on the common "no project state yet" path.
 */
export async function loadSession(
  projectRoot: string = process.cwd(),
): Promise<SessionInfo | null> {
  const { file } = sessionPaths(projectRoot);
  let raw: string;
  try {
    raw = await fs.readFile(file, "utf8");
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw err;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isSessionInfo(parsed)) return null;
  return parsed;
}

/**
 * Persist the session file atomically (tmp + rename). Creates `.speca/` if it
 * does not exist. Does NOT chmod — this is project-local state, not secrets.
 */
export async function saveSession(
  info: SessionInfo,
  projectRoot: string = process.cwd(),
): Promise<void> {
  const { dir, file } = sessionPaths(projectRoot);
  await fs.mkdir(dir, { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`;
  await fs.writeFile(tmp, JSON.stringify(info, null, 2), "utf8");
  try {
    await fs.rename(tmp, file);
  } catch (err) {
    try {
      await fs.unlink(tmp);
    } catch {
      // ignore — surface the rename error
    }
    throw err;
  }
}

/**
 * Remove the session file (used by the `n` keybinding). Returns true when a
 * file was actually deleted.
 */
export async function clearSession(
  projectRoot: string = process.cwd(),
): Promise<boolean> {
  const { file } = sessionPaths(projectRoot);
  try {
    await fs.unlink(file);
    return true;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw err;
  }
}

/**
 * Build a fresh `SessionInfo` for a new session id (does not save). Caller is
 * expected to pass the session id Claude reports back from its first turn.
 */
export function newSessionInfo(
  session_id: string,
  finding_context_bytes = 0,
  now: number = Date.now(),
): SessionInfo {
  return {
    session_id,
    created_at: now,
    last_used_at: now,
    finding_context_bytes,
  };
}

/**
 * Return a copy of `info` with `last_used_at` bumped (and optionally the
 * finding_context_bytes updated). Pure helper.
 */
export function touchSessionInfo(
  info: SessionInfo,
  finding_context_bytes?: number,
  now: number = Date.now(),
): SessionInfo {
  return {
    ...info,
    last_used_at: now,
    finding_context_bytes:
      finding_context_bytes !== undefined ? finding_context_bytes : info.finding_context_bytes,
  };
}

/** Convenience: format `<projectRoot>/.speca/session.json` for log lines. */
export function sessionFilePath(projectRoot: string = process.cwd()): string {
  return sessionPaths(projectRoot).file;
}

/**
 * Type guard re-exported for tests that read raw JSON from disk. Kept here so
 * the validity rule lives in one place.
 */
export const isValidSessionInfo = isSessionInfo;

// Re-export for convenience: callers that take an absolute path can ignore
// projectRoot entirely.
export function pathFor(projectRoot: string): string {
  return sessionFilePath(projectRoot);
}

// Helper for callers that want a parent-directory resolve (e.g. the M5 chat UI
// surfaces this so the user can see where they're working).
export function projectRootFromCwd(): string {
  return resolve(process.cwd());
}

// `dirname` is exported only to keep tests from re-implementing path math.
export { dirname as _dirname };
