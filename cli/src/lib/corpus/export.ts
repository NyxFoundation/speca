/**
 * `speca corpus export` orchestration.
 *
 * Layout of the produced directory (default `<cwd>/speca-corpus-<run-id>/`):
 *
 *   manifest.json                         filtered to included phases
 *   inputs/env.json                       verbatim
 *   prompts/<phase>.md                    one per included phase
 *   phases/<phase>/partials/*.json        verbatim
 *   phases/<phase>/cost.json              verbatim
 *   phases/<phase>/logs/*.jsonl           only when --include-logs (redacted)
 *   phases/01b/graphs/...                 verbatim (Mermaid + invariant notes)
 *   CORPUS_README.md                      provenance + redaction summary
 *
 * The default `--phases` set is `01a,01b,01e` (spec-derived corpus).
 * `02c`/`03`/`04` require `--unsafe-include-findings` because those phases
 * touch target code and have separate disclosure rules.
 */
import { cp, mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";

import { archiveRoot } from "./paths.js";
import { readManifest, deriveStatus } from "./manifest.js";
import type { RunManifest } from "./manifest.js";
import { redactLogFile } from "./redact.js";
import type { RedactionPolicy, RedactionStats } from "./redact.js";

export const DEFAULT_EXPORT_PHASES = ["01a", "01b", "01e"] as const;
const FINDINGS_PHASES = new Set(["02c", "03", "04"]);

export interface CorpusExportOptions {
  runId: string;
  outDir?: string;
  includeLogs: boolean;
  phases: readonly string[];
  unsafeIncludeFindings: boolean;
  force: boolean;
  archiveRootOverride?: string;
}

export interface CorpusExportResult {
  outDir: string;
  manifest: RunManifest;
  phasesExported: string[];
  /** Per-phase redaction stats keyed by phase id (only present when logs included). */
  redactionStats: Record<string, RedactionStats>;
  filesCopied: number;
}

export async function exportRun(opts: CorpusExportOptions): Promise<CorpusExportResult> {
  const root = archiveRoot(opts.archiveRootOverride);
  const runDir = join(root, opts.runId);
  const manifestPath = join(runDir, "manifest.json");

  // 1. Validate the source archive.
  try {
    await stat(manifestPath);
  } catch {
    throw new Error(`run-id not found at ${runDir}`);
  }
  const manifest = await readManifest(manifestPath);

  // 2. Resolve target phases + gate findings.
  const requested = opts.phases.length === 0 ? [...DEFAULT_EXPORT_PHASES] : [...opts.phases];
  for (const p of requested) {
    if (FINDINGS_PHASES.has(p) && !opts.unsafeIncludeFindings) {
      throw new Error(
        `phase ${p} is gated behind --unsafe-include-findings (target-code data, ` +
          `subject to bug-bounty disclosure rules).`,
      );
    }
  }

  // 3. Resolve output dir + overwrite gate.
  const outDir = opts.outDir ?? join(process.cwd(), `speca-corpus-${opts.runId}`);
  if (!opts.force) {
    let exists = false;
    try {
      await stat(outDir);
      exists = true;
    } catch {
      /* ok */
    }
    if (exists) {
      throw new Error(
        `${outDir} already exists. Pass --force to overwrite, or pick another --out path.`,
      );
    }
  }
  await mkdir(outDir, { recursive: true });

  // 4. Copy inputs/ with env.json filtered through a key allowlist.
  // The Python orchestrator's _build_env_snapshot today writes only
  // non-sensitive keys (KEYWORDS / SPEC_URLS / SPECA_OUTPUT_DIR /
  // SPECA_01A_SCOPE / ORCHESTRATOR_RUNNER / phases) but we don't want a
  // future expansion (e.g. PAT, ANTHROPIC_API_KEY) to ship verbatim. The
  // allowlist is *intersected* with the on-disk keys so unknown additions
  // are dropped silently — operators can opt them back in by widening the
  // list here once they're audited.
  const inputsSrc = join(runDir, "inputs");
  if (await dirExists(inputsSrc)) {
    await mkdir(join(outDir, "inputs"), { recursive: true });
    const envSrc = join(inputsSrc, "env.json");
    if (await fileExists(envSrc)) {
      const sanitised = await sanitiseEnvJson(envSrc);
      await writeFile(join(outDir, "inputs", "env.json"), sanitised, "utf8");
    }
    // Any other inputs/* files (BUG_BOUNTY_SCOPE snapshot, TARGET_INFO
    // snapshot, etc.) ship verbatim — they are themselves the spec the
    // operator wants to share. Iterate explicitly so we never recurse into
    // an unexpected subdirectory tree.
    const entries = await readdir(inputsSrc, { withFileTypes: true });
    for (const e of entries) {
      if (!e.isFile() || e.name === "env.json") continue;
      await cp(join(inputsSrc, e.name), join(outDir, "inputs", e.name), { force: true });
    }
  }

  let filesCopied = 0;

  // 5. Per-phase copy + (optional) redacted log mirror.
  const targetRepoPath = pickTargetRepoPath(manifest);
  const redactPolicy: RedactionPolicy = { targetRepoPath };
  const redactionStats: Record<string, RedactionStats> = {};
  const phasesExported: string[] = [];
  for (const phase of requested) {
    const srcPhase = join(runDir, "phases", phase);
    if (!(await dirExists(srcPhase))) continue;
    phasesExported.push(phase);

    const destPhase = join(outDir, "phases", phase);
    await mkdir(destPhase, { recursive: true });

    // partials/
    const partialsSrc = join(srcPhase, "partials");
    if (await dirExists(partialsSrc)) {
      await cp(partialsSrc, join(destPhase, "partials"), {
        recursive: true,
        force: true,
      });
      filesCopied += await countFiles(partialsSrc);
    }
    // cost.json
    const costSrc = join(srcPhase, "cost.json");
    if (await fileExists(costSrc)) {
      await cp(costSrc, join(destPhase, "cost.json"), { force: true });
      filesCopied += 1;
    }
    // graphs/ (01b only in practice; copy verbatim so subgraphs ship)
    const graphsSrc = join(srcPhase, "graphs");
    if (await dirExists(graphsSrc)) {
      await cp(graphsSrc, join(destPhase, "graphs"), {
        recursive: true,
        force: true,
      });
      filesCopied += await countFilesRecursive(graphsSrc);
    }
    // logs/ — redacted only when explicitly requested.
    if (opts.includeLogs) {
      const logsSrc = join(srcPhase, "logs");
      if (await dirExists(logsSrc)) {
        const logsDest = join(destPhase, "logs");
        await mkdir(logsDest, { recursive: true });
        const entries = await readdir(logsSrc);
        const phaseStats: RedactionStats = {
          inputLines: 0,
          keptLines: 0,
          droppedToolUseByPath: 0,
          malformedLines: 0,
          unfilteredReadGrepGlob: 0,
        };
        for (const name of entries) {
          if (!name.endsWith(".jsonl")) continue;
          const single = await redactLogFile(
            join(logsSrc, name),
            join(logsDest, name),
            redactPolicy,
          );
          phaseStats.inputLines += single.inputLines;
          phaseStats.keptLines += single.keptLines;
          phaseStats.droppedToolUseByPath += single.droppedToolUseByPath;
          phaseStats.malformedLines += single.malformedLines;
          phaseStats.unfilteredReadGrepGlob += single.unfilteredReadGrepGlob;
          filesCopied += 1;
        }
        redactionStats[phase] = phaseStats;
      }
    }
    // prompts/<phase>.md
    const promptSrc = join(runDir, "prompts", `${phase}.md`);
    if (await fileExists(promptSrc)) {
      const promptDest = join(outDir, "prompts", `${phase}.md`);
      await mkdir(dirname(promptDest), { recursive: true });
      await cp(promptSrc, promptDest, { force: true });
      filesCopied += 1;
    }
  }

  // 6. Filtered manifest write.
  // Strip target_info.repo_path (absolute local filesystem path — would
  // reveal the auditor's homedir) and truncate notes so a Python stack
  // trace doesn't ride along. Keep target_info.target_repo (slug) and
  // .target_commit because those are useful provenance.
  const filteredManifest: Record<string, unknown> = {
    ...manifest,
    phases_completed: phasesExported,
    model: pickPhases(manifest.model, phasesExported),
    prompt_shas: pickPhases(manifest.prompt_shas, phasesExported),
    notes: safeNotesForReadme(manifest.notes) || (manifest.notes ?? ""),
    target_info: sanitiseTargetInfo(manifest.target_info),
  };
  await writeFile(
    join(outDir, "manifest.json"),
    JSON.stringify(filteredManifest, null, 2),
    "utf8",
  );

  // 7. README.
  const readme = renderReadme(manifest, {
    phasesExported,
    includeLogs: opts.includeLogs,
    targetRepoPath,
    unsafeIncludeFindings: opts.unsafeIncludeFindings,
    redactionStats,
  });
  await writeFile(join(outDir, "CORPUS_README.md"), readme, "utf8");

  return {
    outDir,
    manifest,
    phasesExported,
    redactionStats,
    filesCopied,
  };
}

function pickPhases<T>(
  obj: Record<string, T> | undefined | null,
  keep: readonly string[],
): Record<string, T> {
  const out: Record<string, T> = {};
  if (!obj) return out;
  for (const k of keep) {
    if (k in obj) out[k] = obj[k];
  }
  return out;
}

function pickTargetRepoPath(manifest: RunManifest): string | null {
  // Only `target_info.repo_path` is a filesystem path. `target_info.target_repo`
  // is a `<owner>/<name>` slug — feeding it to path.relative would produce
  // garbage matches against `<cwd>/<owner>/<name>` and silently disable
  // redaction while still labelling the export "redacted". Refuse the slug.
  const ti = manifest.target_info;
  if (!ti || typeof ti !== "object") return null;
  const repoPath = (ti as Record<string, unknown>).repo_path;
  return typeof repoPath === "string" && repoPath.trim() ? repoPath : null;
}

/**
 * Allow-listed keys for `inputs/env.json` exported to the corpus. Anything
 * outside this list is dropped during export to keep secrets from leaking
 * through if the upstream `_build_env_snapshot` is widened later.
 */
const ENV_JSON_ALLOWLIST = new Set([
  "KEYWORDS",
  "SPEC_URLS",
  "SPECA_OUTPUT_DIR",
  "SPECA_01A_SCOPE",
  "ORCHESTRATOR_RUNNER",
  "phases",
]);

async function sanitiseEnvJson(srcPath: string): Promise<string> {
  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(await readFile(srcPath, "utf8")) as Record<string, unknown>;
  } catch {
    // Refuse to ship anything we couldn't parse — emit an empty object plus
    // a comment-ish key so the consumer notices the inputs were dropped.
    return JSON.stringify({ _redacted: "env.json was unreadable on export" }, null, 2) + "\n";
  }
  const out: Record<string, unknown> = {};
  const dropped: string[] = [];
  for (const [k, v] of Object.entries(parsed)) {
    if (ENV_JSON_ALLOWLIST.has(k)) {
      out[k] = v;
    } else {
      dropped.push(k);
    }
  }
  if (dropped.length > 0) {
    out._redacted_keys = dropped.sort();
  }
  return JSON.stringify(out, null, 2) + "\n";
}

/**
 * Manifest.notes is a free-form Python-side string ("ok" or
 * "error: <reason>") that may include stack traces / paths / stderr
 * fragments on failure. Truncate the reason to a short prefix before
 * rendering it into the corpus README so we don't ship arbitrary stderr.
 */
/**
 * Strip the `repo_path` key from `target_info` because it is an absolute
 * filesystem path on the auditor's machine — leaks the homedir layout to
 * the corpus consumer. Slug + commit are kept.
 */
function sanitiseTargetInfo(ti: unknown): unknown {
  if (!ti || typeof ti !== "object") return ti ?? null;
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(ti as Record<string, unknown>)) {
    if (k === "repo_path") continue;
    out[k] = v;
  }
  return out;
}

function safeNotesForReadme(notes: string | null | undefined): string {
  if (!notes) return "";
  const trimmed = notes.trim();
  if (trimmed.toLowerCase() === "ok") return "";
  // Keep at most the first 120 chars on the first line — enough to surface
  // the error category without leaking traces.
  const firstLine = trimmed.split(/\r?\n/, 1)[0] ?? "";
  const cap = 120;
  return firstLine.length > cap ? `${firstLine.slice(0, cap)}…` : firstLine;
}

async function dirExists(path: string): Promise<boolean> {
  try {
    const s = await stat(path);
    return s.isDirectory();
  } catch {
    return false;
  }
}

async function fileExists(path: string): Promise<boolean> {
  try {
    const s = await stat(path);
    return s.isFile();
  } catch {
    return false;
  }
}

async function countFiles(dir: string): Promise<number> {
  try {
    const entries = await readdir(dir);
    return entries.length;
  } catch {
    return 0;
  }
}

async function countFilesRecursive(dir: string): Promise<number> {
  let n = 0;
  try {
    const entries = await readdir(dir, { withFileTypes: true });
    for (const e of entries) {
      const p = join(dir, e.name);
      if (e.isDirectory()) {
        n += await countFilesRecursive(p);
      } else {
        n += 1;
      }
    }
  } catch {
    /* ignore */
  }
  return n;
}

function renderReadme(
  manifest: RunManifest,
  ctx: {
    phasesExported: string[];
    includeLogs: boolean;
    targetRepoPath: string | null;
    unsafeIncludeFindings: boolean;
    redactionStats: Record<string, RedactionStats>;
  },
): string {
  const status = deriveStatus(manifest);
  const lines: string[] = [];
  lines.push(`# SPECA Corpus Export — ${manifest.run_id}`);
  lines.push("");
  lines.push("This directory was produced by `speca corpus export`. It is a");
  lines.push("redacted slice of a per-run trace archive from the SPECA pipeline.");
  lines.push("");
  lines.push("## Provenance");
  lines.push("");
  lines.push(`- run_id: \`${manifest.run_id}\``);
  const noteSummary = safeNotesForReadme(manifest.notes);
  lines.push(`- status: ${status}${noteSummary ? ` (notes: ${noteSummary})` : ""}`);
  lines.push(`- started_at: ${manifest.started_at}`);
  lines.push(`- ended_at:   ${manifest.ended_at ?? "—"}`);
  lines.push(`- speca_commit: ${manifest.speca_commit || "—"}`);
  lines.push(`- cost_usd_total (full run): \$${(manifest.cost_usd_total ?? 0).toFixed(4)}`);
  lines.push("");
  lines.push("## Phases included");
  lines.push("");
  lines.push(ctx.phasesExported.length ? ctx.phasesExported.map((p) => `- ${p}`).join("\n") : "- (none — nothing copied)");
  if (ctx.unsafeIncludeFindings) {
    lines.push("");
    lines.push("> WARNING: `--unsafe-include-findings` was set. This export contains");
    lines.push("> target-code data from Phase 02c/03/04 and may be subject to");
    lines.push("> bug-bounty disclosure rules.");
  }
  lines.push("");
  lines.push("## Spec sources");
  lines.push("");
  if (manifest.spec_sources.length === 0) {
    lines.push("- (none captured in manifest)");
  } else {
    for (const u of manifest.spec_sources) lines.push(`- ${u}`);
  }
  lines.push("");
  lines.push("## Log redaction");
  lines.push("");
  if (!ctx.includeLogs) {
    lines.push("Logs were not included in this export (`--include-logs` was not set).");
  } else if (ctx.targetRepoPath === null) {
    lines.push("Logs included, but path-based redaction was **disabled** because the manifest");
    lines.push("did not record `target_info.repo_path`. Read/Grep/Glob tool_use events are");
    lines.push("present verbatim — review before sharing externally.");
  } else {
    lines.push(`Logs included. Path-based redaction was anchored at \`${ctx.targetRepoPath}\`.`);
    lines.push("`tool_use` events with name in {Read, Grep, Glob} whose target path resolved");
    lines.push("under that root were dropped.");
    lines.push("");
    lines.push("Per-phase redaction counts:");
    lines.push("");
    lines.push("| phase | input lines | kept | dropped (path) | malformed | unfiltered R/G/G |");
    lines.push("|---|---|---|---|---|---|");
    for (const phase of ctx.phasesExported) {
      const s = ctx.redactionStats[phase];
      if (!s) continue;
      lines.push(
        `| ${phase} | ${s.inputLines} | ${s.keptLines} | ${s.droppedToolUseByPath} | ${s.malformedLines} | ${s.unfilteredReadGrepGlob} |`,
      );
    }
  }
  lines.push("");
  lines.push("## How to consume");
  lines.push("");
  lines.push("Subgraphs land under `phases/01b/graphs/<batch>/<spec>/SG-*.mmd`,");
  lines.push("formal properties under `phases/01e/partials/*.json`, and discovery");
  lines.push("state under `phases/01a/partials/*.json`. The rendered worker prompts");
  lines.push("used to generate them are in `prompts/<phase>.md`.");
  lines.push("");
  lines.push("Generated by `speca corpus export` — see");
  lines.push("https://github.com/NyxFoundation/speca for the source.");
  return lines.join("\n") + "\n";
}
