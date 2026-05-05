/**
 * Zod schemas for NDJSON pipeline events emitted by `run_phase.py --json`.
 *
 * Event shape: {"type": <event-type>, "ts": <iso-utc>, ...payload}
 *
 * Ref: scripts/orchestrator/json_events.py
 */
import { z } from "zod";

const BaseEvent = z.object({
  type: z.string(),
  ts: z.string(),
});

export const PipelineStartedEvent = BaseEvent.extend({
  type: z.literal("pipeline-started"),
  phases: z.array(z.string()),
  workers: z.number(),
  max_concurrent: z.number(),
  force: z.boolean(),
});

export const PhaseStartedEvent = BaseEvent.extend({
  type: z.literal("phase-started"),
  phase: z.string(),
  workers: z.number(),
  max_concurrent: z.number(),
  force: z.boolean(),
  model: z.string().optional(),
});

export const PhaseCompletedEvent = BaseEvent.extend({
  type: z.literal("phase-completed"),
  phase: z.string(),
  duration_s: z.number(),
  total_results: z.number(),
});

export const PhaseFailedEvent = BaseEvent.extend({
  type: z.literal("phase-failed"),
  phase: z.string(),
  reason: z.string(),
  duration_s: z.number(),
});

export const BudgetExceededEvent = BaseEvent.extend({
  type: z.literal("budget-exceeded"),
  phase: z.string(),
  cost_usd: z.number(),
  max_budget_usd: z.number(),
  duration_s: z.number(),
});

export const CircuitBreakerEvent = BaseEvent.extend({
  type: z.literal("circuit-breaker-tripped"),
  phase: z.string(),
  reason: z.string(),
  stats: z.unknown().optional(),
  duration_s: z.number(),
});

export const PipelineCompletedEvent = BaseEvent.extend({
  type: z.literal("pipeline-completed"),
  phases: z.array(z.string()),
  results: z.unknown().optional(),
  duration_s: z.number(),
});

export const PipelineEvent = z.discriminatedUnion("type", [
  PipelineStartedEvent,
  PhaseStartedEvent,
  PhaseCompletedEvent,
  PhaseFailedEvent,
  BudgetExceededEvent,
  CircuitBreakerEvent,
  PipelineCompletedEvent,
]);

export type PipelineEvent = z.infer<typeof PipelineEvent>;

/**
 * Parse a single NDJSON line into a typed PipelineEvent.
 * Returns null for unparseable lines (e.g. non-JSON stderr leaks).
 */
export function parseEventLine(line: string): PipelineEvent | null {
  const trimmed = line.trim();
  if (!trimmed || !trimmed.startsWith("{")) return null;
  try {
    const raw = JSON.parse(trimmed);
    const result = PipelineEvent.safeParse(raw);
    return result.success ? result.data : null;
  } catch {
    return null;
  }
}
