/**
 * Filter + render timing over the full Sherlock-RQ1 Phase 04 fixture set
 * (issue #29 action item 3).
 *
 * NOT a CI gate — run it locally (or eyeball it in a CI log) to watch for
 * regressions:
 *
 *   $ npm run perf:rq1
 *
 * Reports, over the 102-file / 550-item fixture set:
 *   - loader wall time (glob + JSON parse + Zod + merge)
 *   - per-atom filter latency (averaged over ITERATIONS passes)
 *   - severity sort latency
 *   - initial Ink render of the 148-row prysm browser
 */
import { dirname, join, resolve } from "node:path";
import { performance } from "node:perf_hooks";
import { fileURLToPath } from "node:url";

import { render } from "ink-testing-library";
import { createElement } from "react";

import { FindingBrowser } from "../../src/components/FindingBrowser.js";
import { applyFilter } from "../../src/lib/findings/filter.js";
import { loadFindings } from "../../src/lib/findings/loader.js";
import { sortFindings } from "../../src/lib/findings/sort.js";
import type { Finding } from "../../src/lib/findings/types.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const RQ1 = resolve(__dirname, "..", "fixtures", "sherlock-rq1");
const ITERATIONS = 200;

const FILTER_ATOMS = [
  "severity:High",
  "severity:Critical,High",
  "verdict:CONFIRMED_*",
  "verdict:CONFIRMED_VULNERABILITY,CONFIRMED_POTENTIAL,DOWNGRADED,NEEDS_MANUAL_REVIEW",
  "prop:PROP-57888860*",
  "repo:nethermind_fusaka",
  "text:blob",
  "severity:Medium AND verdict:CONFIRMED_*",
  "NOT verdict:PASS_THROUGH",
];

function ms(v: number): string {
  return `${v.toFixed(2)}ms`;
}

function timeFilter(findings: Finding[], source: string): { avgMs: number; matched: number } {
  // Warm-up parse + one application.
  let matched = applyFilter(findings, source).matched.length;
  const start = performance.now();
  for (let i = 0; i < ITERATIONS; i++) {
    matched = applyFilter(findings, source).matched.length;
  }
  return { avgMs: (performance.now() - start) / ITERATIONS, matched };
}

async function main(): Promise<void> {
  console.log(`RQ1 filter+render benchmark (${ITERATIONS} iterations per atom)`);

  const t0 = performance.now();
  const full = await loadFindings([join(RQ1, "*", "04_PARTIAL_*.json")]);
  const tLoad = performance.now() - t0;
  console.log(
    `load: ${full.files.length} files -> ${full.findings.length} findings in ${ms(tLoad)} (${full.warnings.length} warnings)`,
  );

  const prysm = await loadFindings([join(RQ1, "prysm_fusaka", "04_PARTIAL_*.json")]);
  console.log(`prysm subset: ${prysm.findings.length} findings`);

  console.log("\nfilter atoms (over the combined set):");
  for (const atom of FILTER_ATOMS) {
    const { avgMs, matched } = timeFilter(full.findings, atom);
    console.log(`  ${atom.padEnd(72)} ${ms(avgMs).padStart(9)}  (${matched} matched)`);
  }

  const tSort0 = performance.now();
  for (let i = 0; i < ITERATIONS; i++) {
    sortFindings(full.findings, "severity");
  }
  console.log(`\nseverity sort (${full.findings.length} rows): ${ms((performance.now() - tSort0) / ITERATIONS)} avg`);

  const tRender0 = performance.now();
  const inst = render(
    createElement(FindingBrowser, {
      initial: prysm,
      globs: [join(RQ1, "prysm_fusaka", "04_PARTIAL_*.json")],
      nonInteractive: true,
    }),
  );
  const frame = inst.lastFrame() ?? "";
  const tRender = performance.now() - tRender0;
  inst.unmount();
  console.log(`initial Ink render (prysm, ${prysm.findings.length} rows): ${ms(tRender)} (frame ${frame.length} chars)`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
