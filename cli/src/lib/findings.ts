/**
 * Finding data model and loader for the finding browser (M4).
 *
 * Loads Phase 04 PARTIAL_*.json files and merges into a unified findings list.
 * Also falls back to Phase 03 PARTIAL_*.json if no Phase 04 output exists.
 */
import { promises as fs } from "node:fs";
import { basename, join } from "node:path";
import { z } from "zod";

// ── Severity ordering ──────────────────────────────────────────────────

const SEVERITY_RANK: Record<string, number> = {
  Critical: 4,
  High: 3,
  Medium: 2,
  Low: 1,
  Informational: 0,
};

export function severityRank(severity: string): number {
  return SEVERITY_RANK[severity] ?? -1;
}

// ── Finding shape ──────────────────────────────────────────────────────

export interface Finding {
  propertyId: string;
  checkId: string;
  classification: string;
  severity: string;
  verdict: string;
  summary: string;
  reviewerNotes: string;
  finalRecommendation: string;
  codePath: string;
  codeSnippet: string;
  sourceFile: string;
}

// Lenient Zod schemas (partial fields are common in real outputs)
const CodeScopeZ = z.union([
  z.object({
    locations: z.array(z.object({
      file: z.string().default(""),
      symbol: z.string().default(""),
    })).default([]),
  }),
  z.string(),
]);

const AuditItemZ = z.object({
  property_id: z.string().default(""),
  check_id: z.string().default(""),
  classification: z.string().default(""),
  code_scope: CodeScopeZ.optional(),
  code_path: z.string().optional(),
  code_snippet: z.string().default(""),
  proof_trace: z.string().optional(),
  summary: z.string().default(""),
});

const ReviewedItemZ = z.object({
  property_id: z.string().default(""),
  check_id: z.string().default(""),
  original_finding: z.object({
    classification: z.string().default(""),
    summary: z.string().default(""),
  }).default({ classification: "", summary: "" }),
  review_verdict: z.string().default(""),
  adjusted_severity: z.string().default(""),
  reviewer_notes: z.string().default(""),
  final_recommendation: z.string().default(""),
});

const Phase04PartialZ = z.object({
  reviewed_items: z.array(ReviewedItemZ).default([]),
  source_files: z.array(z.string()).default([]),
});

const Phase03PartialZ = z.object({
  audit_items: z.array(AuditItemZ).default([]),
});

function extractCodePath(item: z.infer<typeof AuditItemZ>): string {
  if (typeof item.code_path === "string" && item.code_path) return item.code_path;
  if (item.code_scope) {
    if (typeof item.code_scope === "string") return item.code_scope;
    const locs = item.code_scope.locations;
    if (locs.length > 0) return locs[0]!.file;
  }
  return "";
}

// ── Loader ─────────────────────────────────────────────────────────────

async function globPartials(dir: string, prefix: string): Promise<string[]> {
  try {
    const entries = await fs.readdir(dir);
    return entries
      .filter((f) => f.startsWith(prefix) && f.endsWith(".json"))
      .sort()
      .map((f) => join(dir, f));
  } catch {
    return [];
  }
}

export async function loadFindings(outputsDir: string): Promise<Finding[]> {
  // Prefer Phase 04 output, fall back to Phase 03
  let files = await globPartials(outputsDir, "04_PARTIAL_");
  if (files.length > 0) {
    return loadPhase04Findings(files);
  }
  files = await globPartials(outputsDir, "03_PARTIAL_");
  if (files.length > 0) {
    return loadPhase03Findings(files);
  }
  return [];
}

async function loadPhase04Findings(files: string[]): Promise<Finding[]> {
  const findings: Finding[] = [];
  for (const file of files) {
    try {
      const raw = JSON.parse(await fs.readFile(file, "utf8"));
      const parsed = Phase04PartialZ.safeParse(raw);
      if (!parsed.success) continue;
      for (const item of parsed.data.reviewed_items) {
        findings.push({
          propertyId: item.property_id,
          checkId: item.check_id,
          classification: item.original_finding.classification,
          severity: item.adjusted_severity,
          verdict: item.review_verdict,
          summary: item.original_finding.summary,
          reviewerNotes: item.reviewer_notes,
          finalRecommendation: item.final_recommendation,
          codePath: "",
          codeSnippet: "",
          sourceFile: basename(file),
        });
      }
    } catch {
      // skip malformed files
    }
  }
  return findings;
}

async function loadPhase03Findings(files: string[]): Promise<Finding[]> {
  const findings: Finding[] = [];
  for (const file of files) {
    try {
      const raw = JSON.parse(await fs.readFile(file, "utf8"));
      const parsed = Phase03PartialZ.safeParse(raw);
      if (!parsed.success) continue;
      for (const item of parsed.data.audit_items) {
        findings.push({
          propertyId: item.property_id,
          checkId: item.check_id,
          classification: item.classification,
          severity: "",
          verdict: "",
          summary: item.summary,
          reviewerNotes: "",
          finalRecommendation: "",
          codePath: extractCodePath(item),
          codeSnippet: item.code_snippet || item.proof_trace || "",
          sourceFile: basename(file),
        });
      }
    } catch {
      // skip malformed files
    }
  }
  return findings;
}

// ── Filter DSL ─────────────────────────────────────────────────────────

export interface FindingFilter {
  severity?: string;
  verdict?: string;
  prop?: string;
  repo?: string;
  text?: string;
}

/**
 * Parse a filter string like "severity:High verdict:Confirmed foo bar"
 * into a structured filter.
 */
export function parseFilter(query: string): FindingFilter {
  const filter: FindingFilter = {};
  const freeText: string[] = [];

  for (const token of query.split(/\s+/)) {
    if (!token) continue;
    const colonIdx = token.indexOf(":");
    if (colonIdx > 0) {
      const key = token.slice(0, colonIdx).toLowerCase();
      const val = token.slice(colonIdx + 1);
      switch (key) {
        case "severity":
          filter.severity = val;
          break;
        case "verdict":
          filter.verdict = val;
          break;
        case "prop":
          filter.prop = val;
          break;
        case "repo":
          filter.repo = val;
          break;
        default:
          freeText.push(token);
      }
    } else {
      freeText.push(token);
    }
  }

  if (freeText.length > 0) {
    filter.text = freeText.join(" ");
  }
  return filter;
}

/**
 * Apply a filter to a list of findings. All conditions are AND-joined.
 */
export function applyFilter(findings: Finding[], filter: FindingFilter): Finding[] {
  return findings.filter((f) => {
    if (filter.severity && !f.severity.toLowerCase().includes(filter.severity.toLowerCase())) return false;
    if (filter.verdict && !f.verdict.toLowerCase().includes(filter.verdict.toLowerCase())) return false;
    if (filter.prop && !f.propertyId.toLowerCase().includes(filter.prop.toLowerCase())) return false;
    if (filter.repo && !f.codePath.toLowerCase().includes(filter.repo.toLowerCase())) return false;
    if (filter.text) {
      const lower = filter.text.toLowerCase();
      const haystack = `${f.summary} ${f.classification} ${f.reviewerNotes} ${f.propertyId}`.toLowerCase();
      if (!haystack.includes(lower)) return false;
    }
    return true;
  });
}

/**
 * Sort findings by severity descending, then by property ID.
 */
export function sortFindings(findings: Finding[]): Finding[] {
  return [...findings].sort((a, b) => {
    const sa = severityRank(a.severity);
    const sb = severityRank(b.severity);
    if (sa !== sb) return sb - sa;
    return a.propertyId.localeCompare(b.propertyId);
  });
}
