/**
 * Friendly names for the SPECA pipeline phases. Mirrors
 * `scripts/orchestrator/config.py::PHASE_CONFIGS` (read-only — the Python
 * side stays the source of truth; we only need labels for the dashboard
 * and this list rarely changes).
 *
 * Unknown phase ids fall back to the id itself so the dashboard still
 * renders cleanly when run against a fork that adds new phases.
 */
export const PHASE_NAMES: Record<string, string> = {
  "01a": "Spec Discovery",
  "01b": "Subgraph Extraction",
  "01e": "Property Generation",
  "02c": "Code Pre-resolution",
  "03": "Audit Map",
  "04": "Audit Review",
};

export function phaseName(id: string): string {
  return PHASE_NAMES[id] ?? id;
}
