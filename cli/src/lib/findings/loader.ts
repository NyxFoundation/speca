/**
 * loader.ts — read Phase 03 / Phase 04 PARTIAL JSON files and merge them
 * into a flat list of {@link Finding} records.
 *
 * Design choices
 * --------------
 * - Validation is lenient: unknown keys are kept (`.passthrough()`), and a file
 *   that fails the top-level shape check is skipped with a warning rather than
 *   aborting the whole load. The Python orchestrator follows the same
 *   "partial-results-are-first-class" rule, so we mirror it here.
 * - Dedup key is `property_id`. If a Phase 04 reviewed item arrives after a
 *   Phase 03 audit item with the same `property_id`, fields are merged and the
 *   review verdict / adjusted severity overwrite the Phase 03 originals.
 * - Files are sorted lexicographically before reading so the import order is
 *   deterministic across OSes — important for the `sort:imported` mode.
 */
import { promises as fs } from "node:fs";
import { resolve, sep } from "node:path";

import fastGlob from "fast-glob";

import {
  type CodeLocationLite,
  type Finding,
  type RawAuditItem,
  type RawPartialFile,
  type RawReviewedItem,
  type Severity,
  normaliseSeverity,
  partialFileSchema,
} from "./types.js";

export interface LoaderWarning {
  file: string;
  message: string;
}

export interface LoadResult {
  findings: Finding[];
  warnings: LoaderWarning[];
  /** Files that were actually opened (after glob expansion + dedup). */
  files: string[];
}

export interface LoadOptions {
  /** Override cwd used for relative glob expansion (defaults to process cwd). */
  cwd?: string;
  /** Pre-resolved file list (skips glob entirely; useful for tests). */
  files?: string[];
}

/**
 * Expand one or more globs into a deduped list of absolute paths.
 *
 * - Honours both single-glob (`outputs/04_PARTIAL_*.json`) and brace-list
 *   (`outputs/{03,04}_PARTIAL_*.json`) patterns.
 * - Skips empty strings.
 */
export async function expandGlobs(patterns: string[], cwd: string = process.cwd()): Promise<string[]> {
  const cleaned = patterns
    .map((p) => p.trim())
    .filter((p) => p.length > 0)
    // fast-glob requires forward slashes even on Windows; normalise so users
    // can paste paths with backslashes.
    .map((p) => p.replace(/\\/g, "/"));
  if (cleaned.length === 0) return [];
  const matches = await fastGlob(cleaned, {
    cwd: cwd.replace(/\\/g, "/"),
    absolute: true,
    onlyFiles: true,
    unique: true,
    objectMode: false,
  });
  // fast-glob always returns forward-slash paths; convert to the platform
  // separator so callers can compare against Node's `path.resolve(...)`.
  const normalised = matches.map((m) => (sep === "\\" ? m.replace(/\//g, "\\") : m));
  normalised.sort();
  return normalised;
}

/**
 * Load + normalise findings from a glob (or pre-resolved file list).
 *
 * Failures during JSON parse / Zod validation produce warnings and are
 * non-fatal. The returned `findings` array is sorted by `importIndex`
 * (i.e. by file order, then by position within the file) so callers can
 * reproduce a stable default ordering.
 */
export async function loadFindings(
  globsOrFiles: string | string[],
  options: LoadOptions = {},
): Promise<LoadResult> {
  const warnings: LoaderWarning[] = [];
  const patterns = Array.isArray(globsOrFiles) ? globsOrFiles : [globsOrFiles];
  const files = options.files
    ? options.files.map((f) => resolve(f))
    : await expandGlobs(patterns, options.cwd ?? process.cwd());

  // Map keyed by property_id so 03/04 records merge.
  const byId = new Map<string, Finding>();
  let importIndex = 0;

  for (const file of files) {
    let raw: string;
    try {
      raw = await fs.readFile(file, "utf8");
    } catch (err) {
      warnings.push({ file, message: `read failed: ${(err as Error).message}` });
      continue;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch (err) {
      warnings.push({ file, message: `JSON parse failed: ${(err as Error).message}` });
      continue;
    }
    const validation = partialFileSchema.safeParse(parsed);
    if (!validation.success) {
      warnings.push({ file, message: `schema check failed: ${validation.error.message}` });
      continue;
    }
    const data: RawPartialFile = validation.data;

    const auditItems = data.audit_items ?? [];
    for (const item of auditItems) {
      mergeAudit(byId, item, file, importIndex++);
    }
    const reviewedItems = data.reviewed_items ?? [];
    for (const item of reviewedItems) {
      mergeReviewed(byId, item, file, importIndex++);
    }
  }

  const findings = [...byId.values()].sort((a, b) => a.importIndex - b.importIndex);
  return { findings, warnings, files };
}

function mergeAudit(
  byId: Map<string, Finding>,
  raw: RawAuditItem,
  file: string,
  importIndex: number,
): void {
  const propertyId = raw.property_id;
  if (!propertyId) return;
  const existing = byId.get(propertyId);
  const locations = extractLocations(raw);
  const severity = normaliseSeverity(existing?.rawSeverity);
  const finding: Finding = existing ?? blankFinding(propertyId, importIndex);

  finding.classification = raw.classification ?? finding.classification;
  finding.summary = pickFirst(finding.summary, raw.summary, raw.proof_trace);
  finding.proofTrace = pickFirst(finding.proofTrace, raw.proof_trace);
  finding.attackScenario = pickFirst(finding.attackScenario, raw.attack_scenario);
  if (locations.length > 0 && finding.allLocations.length === 0) {
    finding.allLocations = locations;
    finding.primaryLocation = locations[0];
  }
  if (!finding.sourceFiles.includes(file)) finding.sourceFiles.push(file);
  finding.searchHaystack = buildHaystack(finding);
  if (!finding.severity && severity) finding.severity = severity as Severity;
  byId.set(propertyId, finding);
}

function mergeReviewed(
  byId: Map<string, Finding>,
  raw: RawReviewedItem,
  file: string,
  importIndex: number,
): void {
  const propertyId = raw.property_id || raw.check_id;
  if (!propertyId) return;
  const existing = byId.get(propertyId);
  const finding: Finding = existing ?? blankFinding(propertyId, importIndex);

  // First-write-wins for the substantive fields; this matches the spirit of
  // resume.py, where the earliest PARTIAL is treated as authoritative.
  if (raw.review_verdict && !finding.verdict) finding.verdict = raw.review_verdict;
  if (raw.adjusted_severity && !finding.rawSeverity) {
    finding.rawSeverity = raw.adjusted_severity;
    const sev = normaliseSeverity(raw.adjusted_severity);
    if (sev) finding.severity = sev as Severity;
  }
  if (raw.original_classification && !finding.classification) {
    finding.classification = raw.original_classification;
  }
  if (raw.original_finding?.summary && !finding.summary) {
    finding.summary = raw.original_finding.summary;
  }
  if (raw.original_finding?.classification && !finding.classification) {
    finding.classification = raw.original_finding.classification;
  }
  if (raw.reviewer_notes && !finding.reviewerNotes) finding.reviewerNotes = raw.reviewer_notes;
  if (raw.final_recommendation && !finding.finalRecommendation) {
    finding.finalRecommendation = raw.final_recommendation;
  }
  if (raw.spec_reference && !finding.specReference) finding.specReference = raw.spec_reference;
  if (!finding.summary) {
    // Fallback: synthesize a one-liner from reviewer_notes for table display.
    finding.summary = (raw.reviewer_notes ?? "").split(/(?<=[.!?])\s+/)[0] ?? "";
  }
  if (!finding.sourceFiles.includes(file)) finding.sourceFiles.push(file);
  finding.searchHaystack = buildHaystack(finding);
  byId.set(propertyId, finding);
}

function blankFinding(propertyId: string, importIndex: number): Finding {
  return {
    id: propertyId,
    propertyId,
    severity: "",
    rawSeverity: "",
    verdict: "",
    classification: "",
    summary: "",
    proofTrace: "",
    attackScenario: "",
    reviewerNotes: "",
    finalRecommendation: "",
    specReference: "",
    primaryLocation: null,
    allLocations: [],
    searchHaystack: propertyId.toLowerCase(),
    sourceFiles: [],
    importIndex,
  };
}

function pickFirst(...values: Array<string | undefined | null>): string {
  for (const v of values) {
    if (v && v.trim().length > 0) return v;
  }
  return "";
}

function extractLocations(raw: RawAuditItem): CodeLocationLite[] {
  const out: CodeLocationLite[] = [];
  // Phase 03 audit map item may carry `code_scope` (typed) or `code_path` (string).
  const scope = raw.code_scope;
  if (scope && Array.isArray(scope.locations)) {
    for (const loc of scope.locations) {
      out.push({
        file: loc.file ?? "",
        symbol: loc.symbol ?? "",
        startLine: loc.line_range?.start ?? 0,
        endLine: loc.line_range?.end ?? 0,
        role: loc.role ?? "primary",
      });
    }
  }
  if (out.length === 0 && typeof raw.code_path === "string" && raw.code_path.length > 0) {
    out.push(parseCodePathString(raw.code_path));
  } else if (out.length === 0 && raw.code_path && typeof raw.code_path === "object") {
    const cs = raw.code_path as { locations?: Array<{ file?: string; symbol?: string; line_range?: { start?: number; end?: number }; role?: string }> };
    for (const loc of cs.locations ?? []) {
      out.push({
        file: loc.file ?? "",
        symbol: loc.symbol ?? "",
        startLine: loc.line_range?.start ?? 0,
        endLine: loc.line_range?.end ?? 0,
        role: loc.role ?? "primary",
      });
    }
  }
  return out;
}

/**
 * Parse a Phase 03 `code_path` string of the form
 *   "src/foo.ts::funcName::L11"
 *   "src/foo.ts::funcName:L11-L20"
 *   "src/foo.ts:128-145"
 * into a {@link CodeLocationLite}.  Anything that doesn't match a recognised
 * shape falls back to "file with no symbol/lines".
 */
function parseCodePathString(s: string): CodeLocationLite {
  // Pattern A: file::symbol::Lstart[-Lend] or file::symbol:Lstart[-Lend]
  const a = /^(.+?)(?:::|::)(.+?)(?:::|:)L(\d+)(?:[-–]L?(\d+))?$/.exec(s);
  if (a) {
    return {
      file: a[1],
      symbol: a[2],
      startLine: Number(a[3]),
      endLine: a[4] ? Number(a[4]) : Number(a[3]),
      role: "primary",
    };
  }
  // Pattern B: file:start-end (numeric)
  const b = /^(.+?):(\d+)(?:[-–](\d+))?$/.exec(s);
  if (b) {
    return {
      file: b[1],
      symbol: "",
      startLine: Number(b[2]),
      endLine: b[3] ? Number(b[3]) : Number(b[2]),
      role: "primary",
    };
  }
  return { file: s, symbol: "", startLine: 0, endLine: 0, role: "primary" };
}

function buildHaystack(f: Finding): string {
  const parts = [
    f.propertyId,
    f.summary,
    f.proofTrace,
    f.attackScenario,
    f.reviewerNotes,
    f.finalRecommendation,
    f.classification,
    f.verdict,
    f.specReference,
    f.primaryLocation?.file ?? "",
    f.primaryLocation?.symbol ?? "",
  ];
  return parts.join("\n").toLowerCase();
}
