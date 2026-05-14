/**
 * Stream-JSON log redactor for `speca corpus export`.
 *
 * Reads a JSONL log file line-by-line and emits the lines that survive the
 * redaction policy. Pure TypeScript — no Python dependency.
 *
 * Policy (per issue #32):
 *   - drop `tool_use` events whose tool name ∈ {Read, Grep, Glob} *and*
 *     whose target path resolves under `targetRepoPath` (= the manifest's
 *     `target_info.repo_path`). Keep otherwise.
 *   - keep all `assistant` text and `tool_use` for `mcp__*` and `Write`.
 *   - keep everything else (default-allow) so we don't accidentally strip
 *     future event types.
 *
 * `targetRepoPath === null` means we have no `target_info.repo_path` to
 * compare against, so path-based filtering is disabled — every `Read`/
 * `Grep`/`Glob` event is kept verbatim and a counter is incremented for
 * the README. This matches the issue #32 wording (filtering is conditional
 * on `target_info.repo_path` being present).
 *
 * `isUnderRepo` uses `path.relative` (case-insensitive on Windows) so
 * mixed-separator inputs (`/repo\foo.go` vs `/repo/foo.go`) are normalised
 * consistently. Earlier draft used a manual prefix check that broke on
 * POSIX whenever the target_repo_path or the tool_use path contained the
 * "wrong" separator family.
 */
import { createReadStream } from "node:fs";
import { open } from "node:fs/promises";
import { isAbsolute, relative, resolve as resolvePath } from "node:path";
import { createInterface } from "node:readline";

export interface RedactionPolicy {
  /** Absolute path to the target repo. `null` disables path-based redaction. */
  targetRepoPath: string | null;
}

export interface RedactionStats {
  inputLines: number;
  keptLines: number;
  droppedToolUseByPath: number;
  malformedLines: number;
  /**
   * When `targetRepoPath === null`, this counts how many Read/Grep/Glob
   * events were kept *because* path filtering was disabled. Surfaced in
   * the export README so the corpus consumer knows redaction was partial.
   */
  unfilteredReadGrepGlob: number;
}

interface ToolUseLike {
  type?: string;
  message?: {
    content?: Array<{
      type?: string;
      name?: string;
      input?: Record<string, unknown>;
    }>;
  };
}

const PATH_SENSITIVE_TOOLS = new Set(["Read", "Grep", "Glob"]);

function extractPathHints(input: Record<string, unknown> | undefined): string[] {
  if (!input) return [];
  const out: string[] = [];
  for (const key of ["file_path", "path", "pattern"]) {
    const v = input[key];
    if (typeof v === "string" && v.trim()) {
      out.push(v);
    }
  }
  return out;
}

function isUnderRepo(targetPath: string, repoRoot: string): boolean {
  // Use path.relative to compute the path *inside* repoRoot. If the result
  // starts with ".." or is absolute, the input is outside the repo.
  //
  // We resolve both sides so relative inputs (`outputs/...`) are anchored
  // at the current working directory before comparison. On Windows we
  // additionally lower-case both because the filesystem is case-insensitive
  // (mixed-case input vs lowercased repo_path would otherwise sneak past).
  const absInput = resolvePath(targetPath);
  const absRoot = resolvePath(repoRoot);
  const normInput = process.platform === "win32" ? absInput.toLowerCase() : absInput;
  const normRoot = process.platform === "win32" ? absRoot.toLowerCase() : absRoot;
  if (normInput === normRoot) return true;
  const rel = relative(normRoot, normInput);
  if (!rel) return true;
  if (rel.startsWith("..")) return false;
  if (isAbsolute(rel)) return false;
  return true;
}

function shouldDropToolUse(
  event: ToolUseLike,
  policy: RedactionPolicy,
  stats: RedactionStats,
): boolean {
  const content = event.message?.content;
  if (!Array.isArray(content)) return false;

  for (const block of content) {
    if (block.type !== "tool_use") continue;
    const name = typeof block.name === "string" ? block.name : "";
    if (!PATH_SENSITIVE_TOOLS.has(name)) continue;
    if (policy.targetRepoPath === null) {
      stats.unfilteredReadGrepGlob += 1;
      // No anchor → keep (issue #32 makes path-based redaction conditional).
      continue;
    }
    const hints = extractPathHints(block.input);
    if (hints.some((h) => isUnderRepo(h, policy.targetRepoPath as string))) {
      return true; // drop this whole line
    }
  }
  return false;
}

export async function redactLogFile(
  srcPath: string,
  destPath: string,
  policy: RedactionPolicy,
): Promise<RedactionStats> {
  const stats: RedactionStats = {
    inputLines: 0,
    keptLines: 0,
    droppedToolUseByPath: 0,
    malformedLines: 0,
    unfilteredReadGrepGlob: 0,
  };
  const out = await open(destPath, "w");
  try {
    const rl = createInterface({
      input: createReadStream(srcPath, { encoding: "utf8" }),
      crlfDelay: Infinity,
    });
    for await (const line of rl) {
      stats.inputLines += 1;
      const trimmed = line.trim();
      if (!trimmed) {
        // Preserve blank lines (cheap; keeps line numbers comparable).
        await out.write(line + "\n");
        stats.keptLines += 1;
        continue;
      }
      let parsed: ToolUseLike;
      try {
        parsed = JSON.parse(trimmed) as ToolUseLike;
      } catch {
        // Default-allow: malformed lines pass through. The redactor's job
        // is policy enforcement, not JSONL validation.
        stats.malformedLines += 1;
        stats.keptLines += 1;
        await out.write(line + "\n");
        continue;
      }
      if (shouldDropToolUse(parsed, policy, stats)) {
        stats.droppedToolUseByPath += 1;
        continue;
      }
      stats.keptLines += 1;
      await out.write(line + "\n");
    }
  } finally {
    await out.close();
  }
  return stats;
}

/**
 * Public helper exported for direct unit testing on string input (no fs
 * round-trip). Returns kept lines and stats; callers can join with "\n".
 */
export function redactLinesForTest(
  lines: readonly string[],
  policy: RedactionPolicy,
): { kept: string[]; stats: RedactionStats } {
  const stats: RedactionStats = {
    inputLines: 0,
    keptLines: 0,
    droppedToolUseByPath: 0,
    malformedLines: 0,
    unfilteredReadGrepGlob: 0,
  };
  const kept: string[] = [];
  for (const line of lines) {
    stats.inputLines += 1;
    const trimmed = line.trim();
    if (!trimmed) {
      kept.push(line);
      stats.keptLines += 1;
      continue;
    }
    let parsed: ToolUseLike;
    try {
      parsed = JSON.parse(trimmed) as ToolUseLike;
    } catch {
      stats.malformedLines += 1;
      stats.keptLines += 1;
      kept.push(line);
      continue;
    }
    if (shouldDropToolUse(parsed, policy, stats)) {
      stats.droppedToolUseByPath += 1;
      continue;
    }
    stats.keptLines += 1;
    kept.push(line);
  }
  return { kept, stats };
}
