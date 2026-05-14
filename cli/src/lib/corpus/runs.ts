/**
 * `listRuns` — scan the archive root and return a row per run-id.
 *
 * Tolerates the messy reality of partial / aborted runs:
 *   - missing manifest.json → row with `unreadable: true`
 *   - corrupt JSON / schema mismatch → row with `unreadable: true` + reason
 *   - non-directory entries under the archive root → skipped silently
 *
 * Sorting: descending by `startedAt` (lexicographic on ISO-ish timestamp,
 * which matches chronological because the run-id format is
 * `YYYY-MM-DDTHH-MM-SSZ-...`). Unreadable rows float to the bottom.
 */
import { stat, readdir } from "node:fs/promises";
import { join } from "node:path";

import { readManifest, summarise } from "./manifest.js";
import type { RunSummary } from "./manifest.js";

export async function listRuns(root: string): Promise<RunSummary[]> {
  let entries: string[];
  try {
    entries = await readdir(root);
  } catch (err) {
    const code = (err as NodeJS.ErrnoException).code;
    if (code === "ENOENT") {
      // No archive root yet — treat as an empty corpus, not an error.
      return [];
    }
    throw err;
  }

  const rows: RunSummary[] = [];
  for (const name of entries) {
    if (name.startsWith(".")) continue; // skip dotfiles (e.g. .trash/)
    const runDir = join(root, name);
    let dirStat;
    try {
      dirStat = await stat(runDir);
    } catch {
      continue;
    }
    if (!dirStat.isDirectory()) continue;

    const manifestPath = join(runDir, "manifest.json");
    try {
      const manifest = await readManifest(manifestPath);
      rows.push(summarise(manifest, runDir, manifestPath));
    } catch (err) {
      const reason =
        err instanceof Error ? err.message : String(err);
      rows.push({
        runId: name,
        runDir,
        manifestPath,
        startedAt: "",
        endedAt: null,
        status: "unknown",
        phasesCompleted: [],
        costUsdTotal: 0,
        specaCommit: "",
        targetRepo: null,
        unreadable: true,
        unreadableReason: reason.split("\n")[0],
      });
    }
  }

  // Sort: readable rows first, descending by startedAt; unreadable rows last,
  // sorted by run-id to keep the order stable across listings.
  rows.sort((a, b) => {
    if (a.unreadable !== b.unreadable) return a.unreadable ? 1 : -1;
    if (a.unreadable) return a.runId.localeCompare(b.runId);
    return b.startedAt.localeCompare(a.startedAt);
  });

  return rows;
}
