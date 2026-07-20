/**
 * AUTO-GENERATED — DO NOT EDIT.
 * Source: schemas/events/*.schema.json (Pydantic-derived).
 * Run `npm run sync-schemas` to refresh.
 */

import { z } from "zod";

export const PipelineStartedEventSchema = z.object({ "force": z.boolean(), "max_concurrent": z.number().int().gte(0), "phases": z.array(z.string()), "ts": z.string().describe("RFC 3339 UTC timestamp with millisecond precision."), "type": z.literal("pipeline-started"), "workers": z.number().int().gte(0) });
export type PipelineStartedEvent = z.infer<typeof PipelineStartedEventSchema>;

export const PhaseStartedEventSchema = z.object({ "force": z.boolean(), "max_concurrent": z.number().int().gte(0), "model": z.union([z.string(), z.null()]).default(null), "phase": z.string(), "ts": z.string().describe("RFC 3339 UTC timestamp with millisecond precision."), "type": z.literal("phase-started"), "workers": z.number().int().gte(0) });
export type PhaseStartedEvent = z.infer<typeof PhaseStartedEventSchema>;

export const PhaseCompletedEventSchema = z.object({ "duration_s": z.number().gte(0), "phase": z.string(), "total_results": z.number().int().gte(0), "ts": z.string().describe("RFC 3339 UTC timestamp with millisecond precision."), "type": z.literal("phase-completed") });
export type PhaseCompletedEvent = z.infer<typeof PhaseCompletedEventSchema>;

export const PhaseFailedEventSchema = z.object({ "duration_s": z.number().gte(0), "phase": z.string(), "reason": z.string(), "ts": z.string().describe("RFC 3339 UTC timestamp with millisecond precision."), "type": z.literal("phase-failed") });
export type PhaseFailedEvent = z.infer<typeof PhaseFailedEventSchema>;

export const BudgetExceededEventSchema = z.object({ "cost_usd": z.union([z.number(), z.null()]).default(null), "duration_s": z.number().gte(0), "max_budget_usd": z.union([z.number(), z.null()]).default(null), "phase": z.string(), "ts": z.string().describe("RFC 3339 UTC timestamp with millisecond precision."), "type": z.literal("budget-exceeded") });
export type BudgetExceededEvent = z.infer<typeof BudgetExceededEventSchema>;

export const CircuitBreakerTrippedEventSchema = z.object({ "duration_s": z.number().gte(0), "phase": z.string(), "reason": z.string(), "stats": z.record(z.string(), z.any()).optional(), "ts": z.string().describe("RFC 3339 UTC timestamp with millisecond precision."), "type": z.literal("circuit-breaker-tripped") });
export type CircuitBreakerTrippedEvent = z.infer<typeof CircuitBreakerTrippedEventSchema>;

export const PipelineCompletedEventSchema = z.object({ "duration_s": z.number().gte(0), "phases": z.array(z.string()), "results": z.record(z.string(), z.boolean()), "ts": z.string().describe("RFC 3339 UTC timestamp with millisecond precision."), "type": z.literal("pipeline-completed") });
export type PipelineCompletedEvent = z.infer<typeof PipelineCompletedEventSchema>;

export const WarningEventSchema = z.object({ "message": z.string(), "phase": z.string(), "ts": z.string().describe("RFC 3339 UTC timestamp with millisecond precision."), "type": z.literal("warning") }).describe("Non-fatal degradation the user must see (issue #98).\n\nExample: a phase declares MCP servers that the resolved ``.mcp.json``\ndoes not provide — the pipeline keeps running, but the TUI dashboard\n(whose only inputs are this NDJSON stream and the log tail; orchestrator\nstderr is discarded in TUI mode) must surface the degradation.");
export type WarningEvent = z.infer<typeof WarningEventSchema>;

export const pipelineEventSchema = z.discriminatedUnion("type", [
  PipelineStartedEventSchema,
  PhaseStartedEventSchema,
  PhaseCompletedEventSchema,
  PhaseFailedEventSchema,
  BudgetExceededEventSchema,
  CircuitBreakerTrippedEventSchema,
  PipelineCompletedEventSchema,
  WarningEventSchema,
] as const);
export type PipelineEvent = z.infer<typeof pipelineEventSchema>;
