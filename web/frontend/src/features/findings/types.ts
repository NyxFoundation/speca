// TypeScript mirror of `web/server/schemas/findings.py`.
//
// Keep this file 1:1 with the backend Pydantic models. The list response is
// always wrapped in `{ data, meta }` so the SPA can hand the meta to a
// banner without re-fetching the list.
//
// Why mirror by hand instead of generating? At v0 the surface is tiny and
// codegen would pull a third dependency into the build. Once the OpenAPI
// surface grows past ~5 endpoints we will revisit.

export const SEVERITY_LEVELS = [
  "Critical",
  "High",
  "Medium",
  "Low",
  "Informational",
] as const;
export type Severity = (typeof SEVERITY_LEVELS)[number];

export const KNOWN_VERDICTS = [
  "CONFIRMED_VULNERABILITY",
  "CONFIRMED_POTENTIAL",
  "DISPUTED_FP",
  "DOWNGRADED",
  "NEEDS_MANUAL_REVIEW",
  "PASS_THROUGH",
] as const;
export type KnownVerdict = (typeof KNOWN_VERDICTS)[number];

export function isKnownVerdict(value: string): value is KnownVerdict {
  return (KNOWN_VERDICTS as readonly string[]).includes(value);
}

export const PHASES = ["03", "04"] as const;
export type Phase = (typeof PHASES)[number];

// The wire model — `verdict` is `string` (not `KnownVerdict`) on purpose so
// forks emitting a custom verdict still render. Type-safe call sites pass
// through `isKnownVerdict()` before branching.
export interface Finding {
  run_id: string;
  phase: "03" | "04" | "05";
  property_id: string;
  // Client/target the finding belongs to (from the `outputs/<target>/`
  // subdirectory). `null` for the single-target top-level layout.
  target: string | null;
  severity: Severity;
  verdict: string | null;
  file: string | null;
  line_range: string | null;
  evidence_snippet: string | null;
  proof_trace: string | null;
  gates_passed: string[];
  reviewer_notes: string | null;
  related_past_fixes: string[];
  critique: Record<string, unknown> | null;
}

export interface FindingsMeta {
  data_source: "current_outputs" | "run_scoped";
  count: number;
  // Distinct client/target names across the unfiltered set. Empty for a
  // single-target run (the client filter is then hidden).
  targets: string[];
}

export interface FindingsResponse {
  data: Finding[];
  meta: FindingsMeta;
}

export interface FindingQuery {
  phase?: Phase;
  severity?: Severity;
  verdict?: string;
  target?: string;
}

export const SEVERITY_RANK: Record<Severity, number> = {
  Critical: 0,
  High: 1,
  Medium: 2,
  Low: 3,
  Informational: 4,
};
