import { describe, expect, it } from "vitest";

import { applyFilter, parseFilter } from "../src/lib/findings/filter.js";
import type { Finding } from "../src/lib/findings/types.js";

function mk(partial: Partial<Finding> & { propertyId: string }): Finding {
  return {
    id: partial.propertyId,
    propertyId: partial.propertyId,
    severity: partial.severity ?? "",
    rawSeverity: partial.rawSeverity ?? partial.severity ?? "",
    verdict: partial.verdict ?? "",
    classification: partial.classification ?? "",
    summary: partial.summary ?? "",
    proofTrace: partial.proofTrace ?? "",
    attackScenario: partial.attackScenario ?? "",
    reviewerNotes: partial.reviewerNotes ?? "",
    finalRecommendation: partial.finalRecommendation ?? "",
    specReference: partial.specReference ?? "",
    primaryLocation: partial.primaryLocation ?? null,
    allLocations: partial.allLocations ?? [],
    searchHaystack: (partial.searchHaystack ?? buildSearchHaystack(partial)).toLowerCase(),
    sourceFiles: partial.sourceFiles ?? [],
    importIndex: partial.importIndex ?? 0,
  };
}

function buildSearchHaystack(p: Partial<Finding> & { propertyId: string }): string {
  return [
    p.propertyId,
    p.summary,
    p.proofTrace,
    p.attackScenario,
    p.reviewerNotes,
    p.classification,
    p.verdict,
    p.specReference,
    p.primaryLocation?.file ?? "",
  ]
    .filter(Boolean)
    .join("\n");
}

const FIXTURES: Finding[] = [
  mk({
    propertyId: "PROP-vault-inv-001",
    severity: "High",
    verdict: "CONFIRMED_VULNERABILITY",
    summary: "Reentrancy in withdraw lets attacker drain vault",
    primaryLocation: { file: "contracts/Vault.sol", symbol: "withdraw", startLine: 128, endLine: 145, role: "primary" },
    sourceFiles: ["/repos/lighthouse/outputs/04_PARTIAL_W0B0.json"],
    reviewerNotes: "all 3 gates passed",
  }),
  mk({
    propertyId: "PROP-vault-pre-002",
    severity: "Informational",
    verdict: "DISPUTED_FP",
    summary: "Helper unsafeMint never called from non-test caller",
    sourceFiles: ["/repos/lighthouse/outputs/04_PARTIAL_W0B0.json"],
  }),
  mk({
    propertyId: "PROP-staking-inv-007",
    severity: "Critical",
    verdict: "CONFIRMED_VULNERABILITY",
    summary: "Missing access control on slashValidator()",
    sourceFiles: ["/repos/lighthouse/outputs/04_PARTIAL_W1B0.json"],
  }),
  mk({
    propertyId: "PROP-staking-post-008",
    severity: "Low",
    verdict: "DOWNGRADED",
    summary: "Rate-limited validator influence",
    sourceFiles: ["/repos/geth/outputs/04_PARTIAL_W3B0.json"],
  }),
  mk({
    propertyId: "PROP-misc-asm-099",
    severity: "Informational",
    verdict: "PASS_THROUGH",
    summary: "Trust-model assumption holds",
    sourceFiles: ["/repos/lighthouse/outputs/04_PARTIAL_W2B0.json"],
  }),
];

describe("parseFilter", () => {
  it("returns a tautology predicate for an empty source", () => {
    const r = parseFilter("");
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.predicate(FIXTURES[0])).toBe(true);
  });

  it("severity:Critical matches only Critical findings", () => {
    const { matched } = applyFilter(FIXTURES, "severity:Critical");
    expect(matched.map((f) => f.propertyId)).toEqual(["PROP-staking-inv-007"]);
  });

  it("severity:Critical,High is comma-separated OR", () => {
    const { matched } = applyFilter(FIXTURES, "severity:Critical,High");
    expect(matched.map((f) => f.propertyId).sort()).toEqual([
      "PROP-staking-inv-007",
      "PROP-vault-inv-001",
    ]);
  });

  it("verdict:CONFIRMED_* matches via wildcard", () => {
    const { matched } = applyFilter(FIXTURES, "verdict:CONFIRMED_*");
    expect(matched.length).toBe(2);
    for (const f of matched) {
      expect(f.verdict.startsWith("CONFIRMED_")).toBe(true);
    }
  });

  it("severity:High AND verdict:CONFIRMED_* requires both", () => {
    const { matched } = applyFilter(FIXTURES, "severity:High AND verdict:CONFIRMED_*");
    expect(matched.map((f) => f.propertyId)).toEqual(["PROP-vault-inv-001"]);
  });

  it("implicit AND between space-separated terms behaves like AND", () => {
    const explicit = applyFilter(FIXTURES, "severity:High AND verdict:CONFIRMED_*").matched;
    const implicit = applyFilter(FIXTURES, "severity:High verdict:CONFIRMED_*").matched;
    expect(implicit).toEqual(explicit);
  });

  it("NOT verdict:DISPUTED_FP excludes the disputed FP row", () => {
    const { matched } = applyFilter(FIXTURES, "NOT verdict:DISPUTED_FP");
    expect(matched.find((f) => f.propertyId === "PROP-vault-pre-002")).toBeUndefined();
    expect(matched.length).toBe(FIXTURES.length - 1);
  });

  it("prop:PROP-staking* matches by wildcard on property_id", () => {
    const { matched } = applyFilter(FIXTURES, "prop:PROP-staking*");
    expect(matched.map((f) => f.propertyId).sort()).toEqual([
      "PROP-staking-inv-007",
      "PROP-staking-post-008",
    ]);
  });

  it("repo:geth matches via source file substring", () => {
    const { matched } = applyFilter(FIXTURES, "repo:geth");
    expect(matched.map((f) => f.propertyId)).toEqual(["PROP-staking-post-008"]);
  });

  it("text:reentrancy is case-insensitive substring search", () => {
    const { matched } = applyFilter(FIXTURES, "text:reentrancy");
    expect(matched.map((f) => f.propertyId)).toEqual(["PROP-vault-inv-001"]);
  });

  it("bare word falls back to text search", () => {
    const { matched } = applyFilter(FIXTURES, "validator");
    expect(matched.length).toBeGreaterThanOrEqual(2);
  });

  it("OR keyword unites two clauses", () => {
    const { matched } = applyFilter(FIXTURES, "severity:Low OR severity:Critical");
    expect(matched.map((f) => f.propertyId).sort()).toEqual([
      "PROP-staking-inv-007",
      "PROP-staking-post-008",
    ]);
  });

  it("parens override implicit AND precedence", () => {
    const { matched } = applyFilter(
      FIXTURES,
      "(severity:High OR severity:Critical) AND verdict:CONFIRMED_*",
    );
    expect(matched.map((f) => f.propertyId).sort()).toEqual([
      "PROP-staking-inv-007",
      "PROP-vault-inv-001",
    ]);
  });

  it("returns ok:false on malformed input", () => {
    const r = parseFilter("(severity:High");
    expect(r.ok).toBe(false);
  });
});
