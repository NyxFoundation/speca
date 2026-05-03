/**
 * Build a `<system-context>` prompt prefix from a SPECA finding object.
 *
 * Used by `speca ask` (M5) so Claude sees the finding the user is asking
 * about. Spec reference: docs/SPECA_CLI_SPEC.md §5.5 — token budget is capped
 * at 50 KB by default to avoid blowing the Claude Code context window.
 *
 * Smart-truncation strategy when over cap:
 *   1. Trim the longest free-form fields first (proof_trace, attack_scenario,
 *      summary) to reasonable per-field caps.
 *   2. If still over cap, drop everything except `property_id`, severity, the
 *      first code-path location, and a short summary slice.
 *   3. Always emit a banner line ("Code context truncated to fit 50KB cap")
 *      when any truncation has happened so the user knows context is partial.
 */

export const DEFAULT_MAX_CONTEXT_BYTES = 50_000;

/** Subset of finding fields we actually care about for chat context. */
export interface FindingContextInput {
  // The shape is intentionally permissive — Phase 03 (`AuditMapItem`) and
  // Phase 04 (`ReviewedItem`) findings have slightly different keys, and the
  // M4 finding browser may pass either through verbatim. We pluck what we know
  // about and ignore the rest.
  [key: string]: unknown;

  property_id?: string;
  checklist_id?: string;
  classification?: string;
  severity?: string;
  verdict?: string;
  summary?: string;
  proof_trace?: string;
  attack_scenario?: string;
  code_path?: unknown;
  audit_trail?: unknown;
  bug_bounty_eligible?: boolean;
}

export interface BuildContextOptions {
  /** Max bytes of UTF-8 the rendered context should occupy. */
  maxBytes?: number;
}

export interface BuildContextResult {
  /** Rendered prompt prefix, ready to concatenate with the user question. */
  prompt: string;
  /** UTF-8 byte length of `prompt`. */
  bytes: number;
  /** True when one or more fields were trimmed to fit `maxBytes`. */
  truncated: boolean;
  /** Field names that were trimmed (or emptied) — useful for tests / banners. */
  truncatedFields: string[];
}

const TRUNCATION_BANNER =
  "Code context truncated to fit context cap (some fields were shortened).";

function utf8Length(s: string): number {
  return Buffer.byteLength(s, "utf8");
}

function clip(s: string | undefined, maxChars: number): { value: string; clipped: boolean } {
  if (!s) return { value: "", clipped: false };
  if (s.length <= maxChars) return { value: s, clipped: false };
  // Smart-truncate code-ish blocks: keep the first 5 lines, an ellipsis,
  // and the last 5 lines (matches the "function +/- 5 lines only" hint in
  // the M5 spec).
  const lines = s.split(/\r?\n/);
  if (lines.length > 12) {
    const head = lines.slice(0, 5).join("\n");
    const tail = lines.slice(-5).join("\n");
    const candidate = `${head}\n... [${lines.length - 10} lines elided] ...\n${tail}`;
    if (candidate.length <= maxChars) return { value: candidate, clipped: true };
    // Fallthrough — even the head+tail is too big, hard-clip below.
  }
  return { value: `${s.slice(0, Math.max(0, maxChars - 16))}\n... [truncated]`, clipped: true };
}

function renderCodePath(codePath: unknown): string {
  if (!codePath) return "";
  if (typeof codePath === "string") return codePath;
  // CodeScope shape: { locations: [{file, symbol, line_range:{start,end}}] }
  if (typeof codePath === "object" && codePath !== null) {
    const obj = codePath as { locations?: unknown };
    if (Array.isArray(obj.locations)) {
      const lines: string[] = [];
      for (const loc of obj.locations) {
        if (loc && typeof loc === "object") {
          const l = loc as {
            file?: string;
            symbol?: string;
            line_range?: { start?: number; end?: number };
            note?: string;
            role?: string;
          };
          const range = l.line_range
            ? `:${l.line_range.start ?? "?"}-${l.line_range.end ?? "?"}`
            : "";
          const role = l.role && l.role !== "primary" ? ` (${l.role})` : "";
          lines.push(`- ${l.file ?? "?"}::${l.symbol ?? "?"}${range}${role}`);
        }
      }
      return lines.join("\n");
    }
  }
  // Last-ditch: stringify.
  try {
    return JSON.stringify(codePath, null, 2);
  } catch {
    return String(codePath);
  }
}

interface RenderArgs {
  property_id: string;
  checklist_id: string;
  classification: string;
  severity: string;
  verdict: string;
  summary: string;
  proof_trace: string;
  attack_scenario: string;
  code_path: string;
  truncated: boolean;
}

function renderPrefix(a: RenderArgs): string {
  const parts: string[] = [];
  parts.push("<system-context>");
  parts.push("You are helping audit a security finding from SPECA. Use only");
  parts.push("the information below as authoritative; ask clarifying questions");
  parts.push("if you need details that are not present.");
  parts.push("");
  if (a.truncated) {
    parts.push(`[notice] ${TRUNCATION_BANNER}`);
    parts.push("");
  }
  if (a.property_id) parts.push(`property_id: ${a.property_id}`);
  if (a.checklist_id) parts.push(`checklist_id: ${a.checklist_id}`);
  if (a.severity) parts.push(`severity: ${a.severity}`);
  if (a.verdict) parts.push(`verdict: ${a.verdict}`);
  if (a.classification) parts.push(`classification: ${a.classification}`);
  if (a.summary) {
    parts.push("");
    parts.push("## Summary");
    parts.push(a.summary);
  }
  if (a.proof_trace) {
    parts.push("");
    parts.push("## Proof trace");
    parts.push(a.proof_trace);
  }
  if (a.attack_scenario) {
    parts.push("");
    parts.push("## Attack scenario");
    parts.push(a.attack_scenario);
  }
  if (a.code_path) {
    parts.push("");
    parts.push("## Code locations");
    parts.push(a.code_path);
  }
  parts.push("</system-context>");
  parts.push("");
  return parts.join("\n");
}

/**
 * Build the `<system-context>` prefix for a finding, smart-truncating to fit
 * `maxBytes` (UTF-8). Pure: no I/O.
 */
export function buildFindingContext(
  finding: FindingContextInput,
  options: BuildContextOptions = {},
): BuildContextResult {
  const maxBytes = options.maxBytes ?? DEFAULT_MAX_CONTEXT_BYTES;

  const fields = {
    property_id: String(finding.property_id ?? ""),
    checklist_id: String(finding.checklist_id ?? ""),
    classification: String(finding.classification ?? ""),
    severity: String(finding.severity ?? ""),
    verdict: String(finding.verdict ?? ""),
    summary: typeof finding.summary === "string" ? finding.summary : "",
    proof_trace: typeof finding.proof_trace === "string" ? finding.proof_trace : "",
    attack_scenario:
      typeof finding.attack_scenario === "string" ? finding.attack_scenario : "",
    code_path: renderCodePath(finding.code_path),
  };

  // First pass: render verbatim. If it fits, we're done.
  const initial = renderPrefix({ ...fields, truncated: false });
  if (utf8Length(initial) <= maxBytes) {
    return {
      prompt: initial,
      bytes: utf8Length(initial),
      truncated: false,
      truncatedFields: [],
    };
  }

  // Second pass: clip the long-form fields with progressively tighter caps
  // until we fit, then stop. We prefer to keep summary intact (it is the
  // most useful single field) and shrink proof_trace / attack_scenario /
  // code_path first.
  const truncatedFields: string[] = [];
  const trimSequence: Array<{ key: keyof typeof fields; cap: number }> = [
    { key: "code_path", cap: 4_000 },
    { key: "proof_trace", cap: 8_000 },
    { key: "attack_scenario", cap: 4_000 },
    { key: "summary", cap: 4_000 },
    { key: "code_path", cap: 1_000 },
    { key: "proof_trace", cap: 2_000 },
    { key: "attack_scenario", cap: 1_000 },
    { key: "summary", cap: 1_000 },
    { key: "code_path", cap: 200 },
    { key: "proof_trace", cap: 200 },
    { key: "attack_scenario", cap: 200 },
    { key: "summary", cap: 500 },
  ];

  for (const step of trimSequence) {
    const before = fields[step.key];
    const { value, clipped } = clip(before, step.cap);
    if (clipped) {
      fields[step.key] = value;
      if (!truncatedFields.includes(step.key)) truncatedFields.push(step.key);
    }
    const candidate = renderPrefix({ ...fields, truncated: true });
    if (utf8Length(candidate) <= maxBytes) {
      return {
        prompt: candidate,
        bytes: utf8Length(candidate),
        truncated: true,
        truncatedFields,
      };
    }
  }

  // Last resort: hard-empty everything except the identifiers + banner.
  const stripped = renderPrefix({
    property_id: fields.property_id,
    checklist_id: fields.checklist_id,
    classification: fields.classification,
    severity: fields.severity,
    verdict: fields.verdict,
    summary: clip(fields.summary, 200).value,
    proof_trace: "",
    attack_scenario: "",
    code_path: "",
    truncated: true,
  });
  for (const k of ["proof_trace", "attack_scenario", "code_path"] as const) {
    if (!truncatedFields.includes(k)) truncatedFields.push(k);
  }
  return {
    prompt: stripped,
    bytes: utf8Length(stripped),
    truncated: true,
    truncatedFields,
  };
}

/**
 * Concatenate the `<system-context>` prefix and the user's free-form question
 * into the final prompt that gets piped to `claude -p`.
 */
export function composeAskPrompt(
  finding: FindingContextInput | null,
  question: string,
  options: BuildContextOptions = {},
): { prompt: string; context: BuildContextResult | null } {
  if (!finding) {
    return { prompt: question, context: null };
  }
  const context = buildFindingContext(finding, options);
  return { prompt: `${context.prompt}\n${question}`, context };
}
