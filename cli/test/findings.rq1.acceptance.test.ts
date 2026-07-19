/**
 * M4 acceptance against the FULL Sherlock-RQ1 Phase 04 fixture set
 * (issue #29).
 *
 * Fixture provenance: the `bench-rq1-20260508-sherlock_ethereum_audit_contest`
 * GitHub Release tarball — the collected `outputs/04_PARTIAL_*.json` files of
 * the real RQ1 run over 10 Ethereum-client repos, committed verbatim under
 * `test/fixtures/sherlock-rq1/<repo>/` (plus the nethermind Phase 03 slice
 * for 03↔04 merge / code-location coverage).
 *
 * The RQ1 evaluation counted **72 actionable findings** (CONFIRMED_VULNERABILITY
 * 39, CONFIRMED_POTENTIAL 24, DOWNGRADED 8, NEEDS_MANUAL_REVIEW 1) across
 * 550 reviewed items. `speca browse` operates on one project (= one repo) at
 * a time and property ids repeat across repos (the same property set was
 * audited against every client), so the per-repo loads below are the
 * realistic browsing surface: their actionable counts must sum to 72.
 */
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { render } from "ink-testing-library";
import { createElement } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { FindingBrowser } from "../src/components/FindingBrowser.js";
import { applyFilter } from "../src/lib/findings/filter.js";
import { loadFindings } from "../src/lib/findings/loader.js";
import { sortFindings } from "../src/lib/findings/sort.js";
import { severityRank } from "../src/lib/findings/types.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const RQ1 = resolve(__dirname, "fixtures", "sherlock-rq1");

/** Verdicts the RQ1 evaluation counts as "findings" (actionable). */
const ACTIONABLE_FILTER =
  "verdict:CONFIRMED_VULNERABILITY,CONFIRMED_POTENTIAL,DOWNGRADED,NEEDS_MANUAL_REVIEW";

/** repo → [reviewed items (= findings, no same-repo dupes), actionable]. */
const PER_REPO: Record<string, { findings: number; actionable: number }> = {
  alloy_evm_fusaka: { findings: 81, actionable: 3 },
  c_kzg_4844_fusaka: { findings: 35, actionable: 5 },
  grandine_fusaka: { findings: 74, actionable: 4 },
  lighthouse_fusaka: { findings: 133, actionable: 18 },
  lodestar_fusaka: { findings: 37, actionable: 9 },
  nethermind_fusaka: { findings: 5, actionable: 2 },
  nimbus_fusaka: { findings: 14, actionable: 8 },
  prysm_fusaka: { findings: 148, actionable: 20 },
  reth_fusaka: { findings: 4, actionable: 2 },
  rust_eth_kzg_fusaka: { findings: 19, actionable: 1 },
};

function repoGlob(repo: string): string {
  return join(RQ1, repo, "04_PARTIAL_*.json");
}

function strip(s: string): string {
  return s.replace(/\[[0-9;]*m/g, "");
}

const created: Array<{ unmount: () => void }> = [];
afterEach(() => {
  while (created.length > 0) created.pop()!.unmount();
});

describe("RQ1 fixture set — loader", () => {
  it("loads every repo without a single warning and matches the run's counts", async () => {
    let actionableTotal = 0;
    for (const [repo, expected] of Object.entries(PER_REPO)) {
      const res = await loadFindings([repoGlob(repo)]);
      expect(res.warnings, `${repo} loader warnings`).toEqual([]);
      expect(res.findings.length, `${repo} findings`).toBe(expected.findings);
      const { matched, result } = applyFilter(res.findings, ACTIONABLE_FILTER);
      expect(result.ok).toBe(true);
      expect(matched.length, `${repo} actionable`).toBe(expected.actionable);
      actionableTotal += matched.length;
    }
    // The headline M4 acceptance number: all 72 Sherlock-RQ1 findings.
    expect(actionableTotal).toBe(72);
  });

  it("normalises real-world severity spellings (MEDIUM/HIGH) to the canonical set", async () => {
    // The run contains a handful of upper-cased `adjusted_severity` values
    // (e.g. lighthouse PROP-6a4369e9-inv-010 "HIGH") — none may survive as
    // raw-only after normalisation.
    const all = await loadFindings([join(RQ1, "*", "04_PARTIAL_*.json")]);
    expect(all.files.length).toBe(102);
    expect(all.warnings).toEqual([]);
    const unnormalised = all.findings.filter((f) => !f.severity && f.rawSeverity);
    expect(unnormalised).toEqual([]);
  });

  it("merges the nethermind Phase 03 audit items into the Phase 04 verdicts", async () => {
    const res = await loadFindings([
      join(RQ1, "nethermind_fusaka", "03_PARTIAL_*.json"),
      join(RQ1, "nethermind_fusaka", "04_PARTIAL_*.json"),
    ]);
    expect(res.warnings).toEqual([]);
    expect(res.findings.length).toBe(18);
    // Every 03 item carries a code_path — the browser needs locations for
    // the code-peek modal.
    expect(res.findings.filter((f) => f.primaryLocation !== null).length).toBe(18);
    // The 5 reviewed items all join onto an existing 03 record.
    expect(res.findings.filter((f) => f.verdict !== "").length).toBe(5);
  });
});

describe("RQ1 fixture set — filter atoms (prysm, 148 findings)", () => {
  async function prysm() {
    return loadFindings([repoGlob("prysm_fusaka")]);
  }

  it("severity: atoms", async () => {
    const { findings } = await prysm();
    expect(applyFilter(findings, "severity:Critical").matched.length).toBe(1);
    expect(applyFilter(findings, "severity:High").matched.length).toBe(4);
    expect(applyFilter(findings, "severity:Medium").matched.length).toBe(18);
    // Comma-OR equals the union of the two exact matches.
    expect(applyFilter(findings, "severity:Critical,High").matched.length).toBe(5);
  });

  it("verdict: atoms including wildcard", async () => {
    const { findings } = await prysm();
    expect(applyFilter(findings, "verdict:CONFIRMED_*").matched.length).toBe(15);
    expect(applyFilter(findings, "verdict:DISPUTED_FP").matched.length).toBe(5);
    expect(applyFilter(findings, "verdict:PASS_THROUGH").matched.length).toBe(123);
    // Complement check: NOT of a verdict partitions the set.
    expect(applyFilter(findings, "NOT verdict:PASS_THROUGH").matched.length).toBe(148 - 123);
  });

  it("prop: wildcard atoms", async () => {
    const { findings } = await prysm();
    expect(applyFilter(findings, "prop:PROP-57888860*").matched.length).toBe(50);
    // Every finding carries a PROP- id, so the catch-all matches everything.
    expect(applyFilter(findings, "prop:PROP-*").matched.length).toBe(148);
  });

  it("repo: atom distinguishes repos on a combined load", async () => {
    const all = await loadFindings([join(RQ1, "*", "04_PARTIAL_*.json")]);
    const nether = applyFilter(all.findings, "repo:nethermind_fusaka").matched;
    expect(nether.length).toBe(5);
    expect(nether.every((f) => f.sourceFiles.some((s) => s.includes("nethermind_fusaka")))).toBe(true);
  });

  it("free-text atoms search the real haystack", async () => {
    const { findings } = await prysm();
    const viaField = applyFilter(findings, "text:blob").matched.length;
    const viaBareWord = applyFilter(findings, "blob").matched.length;
    expect(viaField).toBe(10);
    expect(viaBareWord).toBe(viaField);
    // Sanity: the text matches agree with a direct haystack scan.
    expect(findings.filter((f) => f.searchHaystack.includes("blob")).length).toBe(viaField);
  });

  it("composite expressions stay consistent at this scale", async () => {
    const { findings } = await prysm();
    const a = applyFilter(findings, "severity:Medium AND verdict:CONFIRMED_*").matched.length;
    const b = applyFilter(findings, "(severity:Medium) AND (verdict:CONFIRMED_*)").matched.length;
    expect(a).toBe(b);
    expect(a).toBeGreaterThan(0);
    expect(a).toBeLessThanOrEqual(15);
  });
});

describe("RQ1 fixture set — render at scale", () => {
  it("renders the 148-row prysm table windowed, with a correct footer", async () => {
    const initial = await loadFindings([repoGlob("prysm_fusaka")]);
    const inst = render(
      createElement(FindingBrowser, {
        initial,
        globs: [repoGlob("prysm_fusaka")],
        nonInteractive: true,
      }),
    );
    created.push(inst);
    const out = strip(inst.lastFrame() ?? "");
    expect(out).toContain("148 findings");
    // The viewport must window the table instead of flooding the terminal.
    expect(out).toMatch(/showing 1-\d+ of 148/);
    const dataRows = out.split("\n").filter((l) => l.includes("PROP-"));
    // viewportHeight=10 plus the detail pane's property line — never 148 rows.
    expect(dataRows.length).toBeLessThanOrEqual(12);
  });

  it("orders the default severity sort correctly across all 148 findings", async () => {
    const { findings } = await loadFindings([repoGlob("prysm_fusaka")]);
    const sorted = sortFindings(findings, "severity");
    expect(sorted.length).toBe(148);
    for (let i = 1; i < sorted.length; i++) {
      expect(
        severityRank(sorted[i - 1].severity),
        `row ${i - 1} (${sorted[i - 1].id}) vs row ${i} (${sorted[i].id})`,
      ).toBeLessThanOrEqual(severityRank(sorted[i].severity));
    }
    // The single Critical finding leads the table.
    expect(sorted[0].severity).toBe("Critical");
  });

  it("pre-filtered render: the 20 actionable prysm findings all fit the browser", async () => {
    const initial = await loadFindings([repoGlob("prysm_fusaka")]);
    const inst = render(
      createElement(FindingBrowser, {
        initial,
        globs: [repoGlob("prysm_fusaka")],
        initialFilter: ACTIONABLE_FILTER,
        nonInteractive: true,
      }),
    );
    created.push(inst);
    const out = strip(inst.lastFrame() ?? "");
    expect(out).toContain("20 / 148");
    expect(out).toMatch(/showing 1-\d+ of 20/);
  });

  it("renders long real-world reviewer notes without crashing the detail pane", async () => {
    // The run's reviewer_notes routinely exceed 1kB (multi-gate analyses,
    // file paths, line references) — the browser must window/truncate, not
    // throw. Load a repo whose notes are among the longest.
    const initial = await loadFindings([repoGlob("lighthouse_fusaka")]);
    const longest = [...initial.findings].sort(
      (a, b) => b.reviewerNotes.length - a.reviewerNotes.length,
    )[0];
    expect(longest.reviewerNotes.length).toBeGreaterThan(500);
    const inst = render(
      createElement(FindingBrowser, {
        initial,
        globs: [repoGlob("lighthouse_fusaka")],
        initialFilter: `prop:${longest.propertyId}`,
        nonInteractive: true,
      }),
    );
    created.push(inst);
    const out = strip(inst.lastFrame() ?? "");
    expect(out).toContain("1 / 133");
    expect(out).toContain(longest.propertyId);
  });
});
