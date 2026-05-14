/**
 * Garbage collection for `.speca/runs/` archives.
 *
 * Run age is determined from `manifest.started_at` (the run-id timestamp is
 * synthesized from it, so they agree). For unreadable archives we fall back
 * to the run-id's leading timestamp segment; if that's also unparseable the
 * archive is reported as `skipped: unreadable` rather than deleted, so the
 * operator can investigate manually.
 *
 * Deletion uses a two-step soft-delete to give a recovery window:
 *   1. Rename `<archiveRoot>/<runId>` → `<archiveRoot>/.trash/<runId>-<ts>`
 *   2. Subsequent `gc --empty-trash` (future slice) hard-deletes the trash.
 *
 * Today step 1 is the only thing implemented — that already prevents
 * accidental data loss from a mistyped `--older-than 1s`.
 */
import { randomBytes } from "node:crypto";
import { mkdir, rename, stat } from "node:fs/promises";
import { join } from "node:path";

import { listRuns } from "./runs.js";
import type { RunSummary } from "./manifest.js";

export type GcAction = "deleted" | "would-delete" | "skipped";

export interface GcCandidate {
  row: RunSummary;
  ageMs: number;
  action: GcAction;
  reason?: string;
}

export interface GcResult {
  candidates: GcCandidate[];
  trashDir: string;
}

/**
 * Plan + execute (or dry-run) GC against the archive at `root`.
 *
 * - `olderThanMs` = positive integer, the inclusive cutoff. `0` would touch
 *    every run, which is almost never what the operator wants, so callers
 *    should reject zero explicitly before calling.
 * - `dryRun` = report what would be deleted without renaming anything.
 */
export async function gcRuns(opts: {
  root: string;
  olderThanMs: number;
  /**
   * Safer default at the function boundary: when `dryRun` is omitted we
   * never destroy data. Callers that want to actually delete must set
   * `dryRun: false` explicitly.
   */
  dryRun?: boolean;
  now?: number;
}): Promise<GcResult> {
  const now = opts.now ?? Date.now();
  const dryRun = opts.dryRun ?? true;
  const rows = await listRuns(opts.root);
  const trashDir = join(opts.root, ".trash");

  const candidates: GcCandidate[] = [];
  for (const row of rows) {
    const ageMs = resolveAgeMs(row, now);
    if (ageMs === null) {
      candidates.push({
        row,
        ageMs: Number.NaN,
        action: "skipped",
        reason: "started_at unreadable, refusing to delete",
      });
      continue;
    }
    if (ageMs < opts.olderThanMs) {
      // Younger than the cutoff — not a deletion target. We omit from
      // candidates entirely; the operator only cares about what's at risk.
      continue;
    }
    if (dryRun) {
      candidates.push({ row, ageMs, action: "would-delete" });
      continue;
    }
    try {
      await mkdir(trashDir, { recursive: true });
      // Per-candidate timestamp + 6-hex random suffix. Two `gc` invocations
      // in the same millisecond — or two candidates within the same call —
      // can never collide on the trash path.
      const stamp = String(Date.now());
      const nonce = randomBytes(3).toString("hex");
      let trashPath = join(trashDir, `${row.runId}-${stamp}-${nonce}`);
      // Belt-and-braces: if the destination somehow exists (clock skew /
      // reused nonce), append a second nonce rather than overwriting.
      try {
        await stat(trashPath);
        trashPath = `${trashPath}-${randomBytes(3).toString("hex")}`;
      } catch {
        /* expected — destination should not exist */
      }
      await rename(row.runDir, trashPath);
      candidates.push({ row, ageMs, action: "deleted" });
    } catch (err) {
      candidates.push({
        row,
        ageMs,
        action: "skipped",
        reason: `rename to trash failed: ${(err as Error).message}`,
      });
    }
  }

  return { candidates, trashDir };
}

function resolveAgeMs(row: RunSummary, now: number): number | null {
  // 1. Manifest started_at — the authoritative source.
  if (row.startedAt) {
    const t = Date.parse(row.startedAt);
    if (Number.isFinite(t)) return now - t;
  }
  // 2. Run-id leading timestamp segment as a fallback (works on partial /
  //    unreadable manifests). Format: YYYY-MM-DDTHH-MM-SSZ-...
  const m = /^(\d{4}-\d{2}-\d{2}T\d{2})-(\d{2})-(\d{2})Z/u.exec(row.runId);
  if (m) {
    const iso = `${m[1]}:${m[2]}:${m[3]}Z`;
    const t = Date.parse(iso);
    if (Number.isFinite(t)) return now - t;
  }
  return null;
}
