/**
 * Manifest reader for `.speca/runs/<run-id>/manifest.json`.
 *
 * Single zod schema kept in lock-step with `scripts/orchestrator/schemas.py`
 * via `cli/scripts/sync-schemas.mjs`. The generated `types.ts` provides the
 * compile-time shape; this module adds runtime validation and a few derived
 * fields (`status`, `targetRepo`) so subcommands can render without doing
 * the same string parsing twice.
 */
import { readFile } from "node:fs/promises";
import { z } from "zod";

/**
 * Lenient zod schema — tolerates extra fields (the Python side may add new
 * provenance keys without breaking older CLI versions) and missing optionals.
 * Mirrors the Pydantic `RunManifest` model in
 * `scripts/orchestrator/schemas.py`.
 */
export const runManifestSchema = z
  .object({
    run_id: z.string().min(1),
    started_at: z.string().min(1),
    ended_at: z.string().nullable().optional(),
    speca_commit: z.string().optional().default(""),
    cli_version: z.string().optional().default(""),
    model: z.record(z.string()).optional().default({}),
    prompt_shas: z.record(z.string()).optional().default({}),
    spec_sources: z.array(z.string()).optional().default([]),
    target_info: z.record(z.unknown()).nullable().optional(),
    bug_bounty_scope_sha: z.string().nullable().optional(),
    phases_completed: z.array(z.string()).optional().default([]),
    cost_usd_total: z.number().optional().default(0),
    notes: z.string().nullable().optional(),
  })
  .passthrough();

export type RunManifest = z.infer<typeof runManifestSchema>;

/**
 * Discrete run status derived from `manifest.notes`.
 *
 * The Python archiver writes `"ok"` on a clean finalize and
 * `"error: <reason>"` when one or more phases failed. We expose this as an
 * enum so list/show can render it consistently without parsing the same
 * string twice.
 */
export type RunStatus = "ok" | "error" | "pending" | "unknown";

export function deriveStatus(manifest: Pick<RunManifest, "notes" | "ended_at">): RunStatus {
  const notes = (manifest.notes ?? "").trim().toLowerCase();
  if (notes === "ok") return "ok";
  if (notes.startsWith("error")) return "error";
  if (!manifest.ended_at) return "pending";
  return "unknown";
}

/**
 * Compact view used by `corpus list` and `corpus gc` planning. Pulls the
 * fields that fit on a single table row + the absolute paths the deletion
 * code needs.
 */
export interface RunSummary {
  runId: string;
  runDir: string;
  manifestPath: string;
  startedAt: string;
  endedAt: string | null;
  status: RunStatus;
  phasesCompleted: readonly string[];
  costUsdTotal: number;
  specaCommit: string;
  targetRepo: string | null;
  unreadable: boolean;
  unreadableReason?: string;
}

export function summarise(manifest: RunManifest, runDir: string, manifestPath: string): RunSummary {
  const targetInfo = manifest.target_info ?? null;
  const targetRepo =
    targetInfo && typeof targetInfo === "object" && typeof (targetInfo as Record<string, unknown>).target_repo === "string"
      ? ((targetInfo as Record<string, unknown>).target_repo as string)
      : null;
  return {
    runId: manifest.run_id,
    runDir,
    manifestPath,
    startedAt: manifest.started_at,
    endedAt: manifest.ended_at ?? null,
    status: deriveStatus(manifest),
    phasesCompleted: manifest.phases_completed ?? [],
    costUsdTotal: manifest.cost_usd_total ?? 0,
    specaCommit: manifest.speca_commit ?? "",
    targetRepo,
    unreadable: false,
  };
}

export async function readManifest(manifestPath: string): Promise<RunManifest> {
  const raw = await readFile(manifestPath, "utf8");
  const parsed = JSON.parse(raw) as unknown;
  return runManifestSchema.parse(parsed);
}
