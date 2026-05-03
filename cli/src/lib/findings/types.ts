/**
 * Type definitions for the M4 finding browser.
 *
 * The CLI consumes Phase 03 (`audit_items[]`) and Phase 04 (`reviewed_items[]`)
 * PARTIAL JSON files emitted by the Python orchestrator. Both shapes coexist
 * because Phase 04 only carries the verdict / severity adjustment — the
 * proof-trace, attack-scenario, and code-path live in the upstream Phase 03
 * record. The browser joins the two by `property_id` so a finding panel can
 * show everything in one place.
 *
 * Keep this file dependency-free: the loader does Zod validation; consumers
 * (UI components, filters) only need the resulting normalized shape.
 */
import { z } from "zod";

// -- Severity ---------------------------------------------------------------

export const SEVERITY_LEVELS = [
  "Critical",
  "High",
  "Medium",
  "Low",
  "Informational",
] as const;
export type Severity = (typeof SEVERITY_LEVELS)[number];

const SEVERITY_RANK: Record<Severity, number> = {
  Critical: 0,
  High: 1,
  Medium: 2,
  Low: 3,
  Informational: 4,
};

export function severityRank(s: Severity | string | undefined | null): number {
  if (!s) return 99;
  const cap = capitalise(String(s));
  if (cap in SEVERITY_RANK) return SEVERITY_RANK[cap as Severity];
  return 99;
}

export function normaliseSeverity(s: string | undefined | null): Severity | "" {
  if (!s) return "";
  const cap = capitalise(String(s).trim());
  return SEVERITY_LEVELS.includes(cap as Severity) ? (cap as Severity) : "";
}

function capitalise(s: string): string {
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}

// -- Raw schemas (lenient -- everything optional, .passthrough() to keep extras) -

const lineRangeSchema = z
  .object({
    start: z.number().int().nonnegative().optional(),
    end: z.number().int().nonnegative().optional(),
  })
  .passthrough();

const codeLocationSchema = z
  .object({
    file: z.string().optional(),
    symbol: z.string().optional(),
    line_range: lineRangeSchema.optional(),
    role: z.string().optional(),
    note: z.string().optional(),
  })
  .passthrough();

const codeScopeSchema = z
  .object({
    locations: z.array(codeLocationSchema).optional(),
    resolution_status: z.string().optional(),
    resolution_error: z.string().optional(),
  })
  .passthrough();

export const auditItemSchema = z
  .object({
    property_id: z.string().min(1),
    check_id: z.string().optional(),
    checklist_id: z.string().optional(),
    classification: z.string().optional(),
    summary: z.string().optional(),
    proof_trace: z.string().optional(),
    attack_scenario: z.string().optional(),
    code_snippet: z.string().optional(),
    code_path: z.union([z.string(), codeScopeSchema]).optional(),
    code_scope: codeScopeSchema.optional(),
    bug_bounty_eligible: z.boolean().optional(),
    audit_trail: z.unknown().optional(),
  })
  .passthrough();
export type RawAuditItem = z.infer<typeof auditItemSchema>;

export const reviewedItemSchema = z
  .object({
    property_id: z.string().optional(),
    check_id: z.string().optional(),
    review_verdict: z.string().optional(),
    adjusted_severity: z.string().optional(),
    original_classification: z.string().optional(),
    original_finding: z
      .object({
        classification: z.string().optional(),
        summary: z.string().optional(),
      })
      .passthrough()
      .optional(),
    reviewer_notes: z.string().optional(),
    final_recommendation: z.string().optional(),
    spec_reference: z.string().optional(),
  })
  .passthrough();
export type RawReviewedItem = z.infer<typeof reviewedItemSchema>;

const partialMetadataSchema = z
  .object({
    phase: z.string().optional(),
    worker_id: z.union([z.string(), z.number()]).optional(),
    batch_index: z.union([z.string(), z.number()]).optional(),
    item_count: z.number().optional(),
    timestamp: z.union([z.string(), z.number()]).optional(),
    processed_ids: z.array(z.string()).optional(),
  })
  .passthrough();

export const partialFileSchema = z
  .object({
    audit_items: z.array(auditItemSchema).optional(),
    reviewed_items: z.array(reviewedItemSchema).optional(),
    metadata: partialMetadataSchema.optional(),
    source_files: z.array(z.string()).optional(),
  })
  .passthrough();
export type RawPartialFile = z.infer<typeof partialFileSchema>;

// -- Normalised finding ----------------------------------------------------

export interface CodeLocationLite {
  file: string;
  symbol: string;
  startLine: number;
  endLine: number;
  role: string;
}

export interface Finding {
  /** Stable identity for dedup + selection. */
  id: string;
  propertyId: string;
  /** Severity used by the table & filter (adjusted_severity > original). */
  severity: Severity | "";
  rawSeverity: string;
  /** UPPER_SNAKE verdict from Phase 04 (if present). */
  verdict: string;
  /** Phase 03 classification (vulnerability / not-a-vulnerability / ...). */
  classification: string;
  /** One-line summary used in the table. */
  summary: string;
  proofTrace: string;
  attackScenario: string;
  reviewerNotes: string;
  finalRecommendation: string;
  specReference: string;
  /** Primary code location (first one, if any). */
  primaryLocation: CodeLocationLite | null;
  allLocations: CodeLocationLite[];
  /** Free-form extras kept around for `text:` filtering. */
  searchHaystack: string;
  /** Provenance — which file the record was loaded from. */
  sourceFiles: string[];
  /** Stable load order to support `sort:imported`. */
  importIndex: number;
}
