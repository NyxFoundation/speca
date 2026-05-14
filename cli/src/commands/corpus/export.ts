/**
 * `speca corpus export <run-id>` — extract a redacted slice for sharing.
 *
 * Plain stdout (no Ink) — scriptable from CI; the user just wants a
 * directory and a confirmation line.
 */
import { exportRun, DEFAULT_EXPORT_PHASES } from "../../lib/corpus/export.js";

export interface CorpusExportFlags {
  out?: string;
  includeLogs?: boolean;
  phases?: string;
  unsafeIncludeFindings?: boolean;
  force?: boolean;
  archiveRoot?: string;
}

export const CORPUS_EXPORT_HELP = `\
speca corpus export — package a redacted slice of a run archive

Usage
  $ speca corpus export <run-id> [flags]

Flags
  --out <path>                     Output directory (default: <cwd>/speca-corpus-<run-id>/)
  --phases <p1,p2,...>             Phases to include (default: 01a,01b,01e)
  --include-logs                   Also copy redacted stream-json logs
  --unsafe-include-findings        Allow 02c/03/04 phases (target-code data)
  --force                          Overwrite an existing --out directory
  --archive-root <path>            Override the archive root

Redaction policy (per issue #32)
  When --include-logs is set, JSONL events are filtered line-by-line:
    drop: tool_use(Read|Grep|Glob) whose target path resolves under
          manifest.target_info.repo_path
    keep: assistant text, mcp__* tool_use, Write tool_use, everything else
  When the manifest lacks target_info.repo_path, path filtering is disabled
  and the README marks the export as 'unfiltered' — review before sharing.

Examples
  $ speca corpus export 2026-05-13T12-25-02Z-6590de5-eip7825-...e2d7
  $ speca corpus export <run-id> --include-logs --out ./shared/eip7825
  $ speca corpus export <run-id> --phases 01a,01b
`;

function parsePhases(raw: string | undefined): readonly string[] {
  if (!raw || !raw.trim()) return DEFAULT_EXPORT_PHASES;
  return raw
    .split(",")
    .map((p) => p.trim())
    .filter((p) => p.length > 0);
}

export async function runCorpusExportCommand(
  runId: string | undefined,
  flags: CorpusExportFlags,
): Promise<number> {
  if (!runId || !runId.trim()) {
    process.stderr.write("error: <run-id> argument is required\n");
    process.stderr.write(CORPUS_EXPORT_HELP);
    return 2;
  }
  try {
    const result = await exportRun({
      runId,
      outDir: flags.out,
      includeLogs: flags.includeLogs === true,
      phases: parsePhases(flags.phases),
      unsafeIncludeFindings: flags.unsafeIncludeFindings === true,
      force: flags.force === true,
      archiveRootOverride: flags.archiveRoot,
    });
    process.stdout.write(`Exported run ${result.manifest.run_id}\n`);
    process.stdout.write(`  out:    ${result.outDir}\n`);
    process.stdout.write(`  phases: ${result.phasesExported.join(",") || "(none)"}\n`);
    process.stdout.write(`  files:  ${result.filesCopied}\n`);
    if (flags.includeLogs) {
      const totals = Object.values(result.redactionStats).reduce(
        (acc, s) => ({
          in: acc.in + s.inputLines,
          kept: acc.kept + s.keptLines,
          dropped: acc.dropped + s.droppedToolUseByPath,
        }),
        { in: 0, kept: 0, dropped: 0 },
      );
      process.stdout.write(
        `  logs:   ${totals.in} lines in, ${totals.kept} kept, ${totals.dropped} dropped by path\n`,
      );
    }
    return 0;
  } catch (err) {
    process.stderr.write(`error: ${(err as Error).message}\n`);
    return 1;
  }
}
