/**
 * NDJSON event schemas emitted by `scripts/run_phase.py --json`.
 *
 * Source of truth: `scripts/orchestrator/event_models.py` (Pydantic). The
 * Zod schemas below are auto-generated from the JSON Schemas exported from
 * that module, via `cli/scripts/sync-schemas.mjs`. A Pydantic-side rename
 * surfaces here as a CLI build error rather than silent runtime drift.
 *
 * Don't add hand-written event schemas in this file — extend
 * `event_models.py` and run `npm run sync-schemas` instead.
 */

import {
  pipelineEventSchema,
  PipelineStartedEventSchema as pipelineStartedSchema,
  PhaseStartedEventSchema as phaseStartedSchema,
  PhaseCompletedEventSchema as phaseCompletedSchema,
  PhaseFailedEventSchema as phaseFailedSchema,
  BudgetExceededEventSchema as budgetExceededSchema,
  CircuitBreakerTrippedEventSchema as circuitBreakerTrippedSchema,
  PipelineCompletedEventSchema as pipelineCompletedSchema,
  WarningEventSchema as warningSchema,
  type PipelineEvent,
  type PipelineStartedEvent,
  type PhaseStartedEvent,
  type PhaseCompletedEvent,
  type PhaseFailedEvent,
  type BudgetExceededEvent,
  type CircuitBreakerTrippedEvent,
  type PipelineCompletedEvent,
  type WarningEvent,
} from "../schemas/generated/events/schemas.js";

export {
  pipelineEventSchema,
  pipelineStartedSchema,
  phaseStartedSchema,
  phaseCompletedSchema,
  phaseFailedSchema,
  budgetExceededSchema,
  circuitBreakerTrippedSchema,
  pipelineCompletedSchema,
  warningSchema,
};
export type {
  PipelineEvent,
  PipelineStartedEvent,
  PhaseStartedEvent,
  PhaseCompletedEvent,
  PhaseFailedEvent,
  BudgetExceededEvent,
  CircuitBreakerTrippedEvent,
  PipelineCompletedEvent,
  WarningEvent,
};

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
