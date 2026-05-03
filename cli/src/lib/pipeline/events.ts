/**
 * NDJSON event schemas emitted by `scripts/run_phase.py --json`.
 *
 * Source of truth: `scripts/orchestrator/json_events.py` (U1, see SPEC §8.4 / §12.1).
 *
 * The Python orchestrator emits one JSON object per line on stdout when
 * invoked with `--json`. Each line carries a `type` discriminator plus
 * type-specific payload fields. We model each event as a Zod schema so the
 * TS side narrows safely and warns (not crashes) on unknown shapes.
 */
import { z } from "zod";

const baseFields = {
  ts: z.string(),
};

export const pipelineStartedSchema = z
  .object({
    type: z.literal("pipeline-started"),
    phases: z.array(z.string()),
    workers: z.number().int().nonnegative(),
    max_concurrent: z.number().int().nonnegative(),
    force: z.boolean(),
    ...baseFields,
  })
  .passthrough();

export const phaseStartedSchema = z
  .object({
    type: z.literal("phase-started"),
    phase: z.string(),
    workers: z.number().int().nonnegative(),
    max_concurrent: z.number().int().nonnegative(),
    force: z.boolean(),
    model: z.string().nullable().optional(),
    ...baseFields,
  })
  .passthrough();

export const phaseCompletedSchema = z
  .object({
    type: z.literal("phase-completed"),
    phase: z.string(),
    duration_s: z.number().nonnegative(),
    total_results: z.number().int().nonnegative(),
    ...baseFields,
  })
  .passthrough();

export const phaseFailedSchema = z
  .object({
    type: z.literal("phase-failed"),
    phase: z.string(),
    reason: z.string(),
    duration_s: z.number().nonnegative(),
    ...baseFields,
  })
  .passthrough();

export const budgetExceededSchema = z
  .object({
    type: z.literal("budget-exceeded"),
    phase: z.string(),
    cost_usd: z.number().nullable().optional(),
    max_budget_usd: z.number().nullable().optional(),
    duration_s: z.number().nonnegative(),
    ...baseFields,
  })
  .passthrough();

export const circuitBreakerTrippedSchema = z
  .object({
    type: z.literal("circuit-breaker-tripped"),
    phase: z.string(),
    reason: z.string(),
    stats: z.record(z.unknown()).optional(),
    duration_s: z.number().nonnegative(),
    ...baseFields,
  })
  .passthrough();

export const pipelineCompletedSchema = z
  .object({
    type: z.literal("pipeline-completed"),
    phases: z.array(z.string()),
    results: z.record(z.boolean()),
    duration_s: z.number().nonnegative(),
    ...baseFields,
  })
  .passthrough();

export const pipelineEventSchema = z.discriminatedUnion("type", [
  pipelineStartedSchema,
  phaseStartedSchema,
  phaseCompletedSchema,
  phaseFailedSchema,
  budgetExceededSchema,
  circuitBreakerTrippedSchema,
  pipelineCompletedSchema,
]);

export type PipelineStartedEvent = z.infer<typeof pipelineStartedSchema>;
export type PhaseStartedEvent = z.infer<typeof phaseStartedSchema>;
export type PhaseCompletedEvent = z.infer<typeof phaseCompletedSchema>;
export type PhaseFailedEvent = z.infer<typeof phaseFailedSchema>;
export type BudgetExceededEvent = z.infer<typeof budgetExceededSchema>;
export type CircuitBreakerTrippedEvent = z.infer<typeof circuitBreakerTrippedSchema>;
export type PipelineCompletedEvent = z.infer<typeof pipelineCompletedSchema>;
export type PipelineEvent = z.infer<typeof pipelineEventSchema>;

export type PipelineEventType = PipelineEvent["type"];

export interface ParseFailure {
  raw: string;
  reason: string;
}

/**
 * Parse a single line of NDJSON into a typed PipelineEvent.
 *
 * Returns `null` for empty lines, malformed JSON, or unknown event types.
 * Callers can pass `onWarn` to surface drops without throwing — the dashboard
 * relies on this to keep streaming through transient garbage.
 */
export function parsePipelineEvent(
  line: string,
  onWarn?: (failure: ParseFailure) => void,
): PipelineEvent | null {
  const trimmed = line.trim();
  if (trimmed === "") return null;

  let raw: unknown;
  try {
    raw = JSON.parse(trimmed);
  } catch (err) {
    onWarn?.({ raw: trimmed, reason: `invalid JSON: ${(err as Error).message}` });
    return null;
  }

  const parsed = pipelineEventSchema.safeParse(raw);
  if (!parsed.success) {
    onWarn?.({
      raw: trimmed,
      reason: `schema mismatch: ${parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`,
    });
    return null;
  }
  return parsed.data;
}

/**
 * Split a chunk of stdout into complete lines (NDJSON style), holding any
 * trailing partial line in the returned `remainder`.
 *
 * Use this when reading from a child-process stream where chunk boundaries
 * do not align with newlines.
 */
export function splitLines(chunk: string, carry: string): { lines: string[]; carry: string } {
  const combined = carry + chunk;
  const parts = combined.split(/\r?\n/);
  const remainder = parts.pop() ?? "";
  return { lines: parts, carry: remainder };
}
