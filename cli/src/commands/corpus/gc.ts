/**
 * `speca corpus gc` — soft-delete runs older than a duration cutoff.
 *
 * Plain stdout (no Ink) — gc is scriptable from CI and the table form is
 * good enough. The default is `--dry-run` so a typo can never delete data.
 */
import { archiveRoot } from "../../lib/corpus/paths.js";
import { parseDuration } from "../../lib/corpus/duration.js";
import { gcRuns } from "../../lib/corpus/gc.js";
import type { GcCandidate } from "../../lib/corpus/gc.js";

export interface CorpusGcFlags {
  olderThan?: string;
  dryRun?: boolean;
  archiveRoot?: string;
}

export const CORPUS_GC_HELP = `\
speca corpus gc — soft-delete runs older than a duration cutoff

Usage
  $ speca corpus gc --older-than <duration> [--dry-run]

Flags
  --older-than <dur>       Required. Format: <int><unit> where unit is one of
                           s | m | h | d | w. Example: 90d, 2w, 36h.
  --dry-run                Print what WOULD be soft-deleted, change nothing.
  --archive-root <path>    Override the archive root (default: SPECA_ARCHIVE_ROOT
                           env or <cwd>/.speca/runs).

Behaviour
  Soft-delete: matching runs are renamed to <archive-root>/.trash/<run-id>-<ts>
  instead of being hard-deleted. Inspect or restore from there manually.

  Age comes from manifest.started_at when readable; otherwise the leading
  timestamp segment of the run-id is used. Runs with neither remain
  in place and are reported as 'skipped: started_at unreadable'.

Examples
  $ speca corpus gc --older-than 90d --dry-run
  $ speca corpus gc --older-than 14d
`;

function formatAge(ms: number): string {
  if (!Number.isFinite(ms)) return "—";
  const d = Math.floor(ms / 86_400_000);
  if (d >= 1) return `${d}d`;
  const h = Math.floor(ms / 3_600_000);
  if (h >= 1) return `${h}h`;
  const m = Math.floor(ms / 60_000);
  return `${m}m`;
}

function actionLabel(c: GcCandidate): string {
  if (c.action === "would-delete") return "WOULD-DELETE";
  if (c.action === "deleted") return "DELETED";
  return `SKIPPED (${c.reason ?? "unknown"})`;
}

export async function runCorpusGcCommand(flags: CorpusGcFlags): Promise<number> {
  if (!flags.olderThan) {
    process.stderr.write("error: --older-than is required\n");
    process.stderr.write(CORPUS_GC_HELP);
    return 2;
  }
  let olderThanMs: number;
  try {
    olderThanMs = parseDuration(flags.olderThan);
  } catch (err) {
    process.stderr.write(`error: ${(err as Error).message}\n`);
    return 2;
  }

  const root = archiveRoot(flags.archiveRoot);
  // dryRun default-on is enforced *inside* gcRuns; we only flip when the
  // user explicitly passes --no-dry-run (meow → dryRun === false).
  const dryRun = flags.dryRun !== false;
  const result = await gcRuns({ root, olderThanMs, dryRun });

  if (result.candidates.length === 0) {
    process.stdout.write(
      `No runs older than ${flags.olderThan} under ${root}\n`,
    );
    return 0;
  }

  process.stdout.write(`Archive root: ${root}\n`);
  process.stdout.write(`Trash dir:    ${result.trashDir}\n`);
  process.stdout.write(
    `Cutoff:       ${flags.olderThan} (${olderThanMs} ms)\n\n`,
  );
  process.stdout.write("AGE   ACTION                          RUN-ID\n");
  for (const c of result.candidates) {
    process.stdout.write(
      `${formatAge(c.ageMs).padEnd(5)} ${actionLabel(c).padEnd(32)}` +
        ` ${c.row.runId}\n`,
    );
  }
  const willDelete = result.candidates.filter((c) => c.action === "would-delete").length;
  const deleted = result.candidates.filter((c) => c.action === "deleted").length;
  if (dryRun) {
    process.stdout.write(
      `\nDry-run: ${willDelete} run(s) would be soft-deleted. ` +
        `Re-run with --no-dry-run to actually move them.\n`,
    );
  } else {
    process.stdout.write(`\nSoft-deleted ${deleted} run(s) into ${result.trashDir}\n`);
  }
  return 0;
}
