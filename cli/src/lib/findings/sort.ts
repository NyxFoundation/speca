/**
 * sort.ts — sort modes for the M4 finding browser.
 *
 * The default mode is `severity` (Critical → Informational, ties broken by
 * import order). `s` cycles through the modes in the order below.
 */
import type { Finding } from "./types.js";
import { severityRank } from "./types.js";

export const SORT_MODES = ["severity", "verdict", "file", "imported"] as const;
export type SortMode = (typeof SORT_MODES)[number];

const VERDICT_RANK: Record<string, number> = {
  CONFIRMED_VULNERABILITY: 0,
  CONFIRMED_POTENTIAL: 1,
  NEEDS_MANUAL_REVIEW: 2,
  DOWNGRADED: 3,
  PASS_THROUGH: 4,
  DISPUTED_FP: 5,
};

export function sortFindings(findings: Finding[], mode: SortMode): Finding[] {
  const copy = [...findings];
  switch (mode) {
    case "severity":
      copy.sort((a, b) => {
        const sa = severityRank(a.severity || a.rawSeverity);
        const sb = severityRank(b.severity || b.rawSeverity);
        if (sa !== sb) return sa - sb;
        return a.importIndex - b.importIndex;
      });
      break;
    case "verdict":
      copy.sort((a, b) => {
        const va = VERDICT_RANK[a.verdict] ?? 99;
        const vb = VERDICT_RANK[b.verdict] ?? 99;
        if (va !== vb) return va - vb;
        return a.importIndex - b.importIndex;
      });
      break;
    case "file":
      copy.sort((a, b) => {
        const fa = a.primaryLocation?.file ?? "";
        const fb = b.primaryLocation?.file ?? "";
        const cmp = fa.localeCompare(fb);
        if (cmp !== 0) return cmp;
        const la = a.primaryLocation?.startLine ?? 0;
        const lb = b.primaryLocation?.startLine ?? 0;
        if (la !== lb) return la - lb;
        return a.importIndex - b.importIndex;
      });
      break;
    case "imported":
      copy.sort((a, b) => a.importIndex - b.importIndex);
      break;
  }
  return copy;
}

export function nextSortMode(current: SortMode): SortMode {
  const idx = SORT_MODES.indexOf(current);
  return SORT_MODES[(idx + 1) % SORT_MODES.length];
}
