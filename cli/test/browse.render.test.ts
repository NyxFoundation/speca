import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { render } from "ink-testing-library";
import { createElement } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { FindingBrowser } from "../src/components/FindingBrowser.js";
import { buildInitialFilter } from "../src/commands/browse.js";
import { loadFindings } from "../src/lib/findings/loader.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURES = resolve(__dirname, "fixtures");

const created: Array<{ unmount: () => void }> = [];

afterEach(() => {
  while (created.length > 0) created.pop()!.unmount();
});

async function loadAll() {
  return loadFindings([
    join(FIXTURES, "03_PARTIAL_*.json"),
    join(FIXTURES, "04_PARTIAL_*.json"),
  ]);
}

function strip(s: string): string {
  // Strip ANSI escapes so assertions don't depend on the user's terminal.
  return s.replace(/\[[0-9;]*m/g, "");
}

describe("FindingBrowser render", () => {
  it("renders the table with severity labels and property ids", async () => {
    const initial = await loadAll();
    const inst = render(
      createElement(FindingBrowser, {
        initial,
        globs: [join(FIXTURES, "04_PARTIAL_*.json")],
        nonInteractive: true,
      }),
    );
    created.push(inst);
    const out = strip(inst.lastFrame() ?? "");
    expect(out).toContain("speca browse");
    expect(out).toContain("PROP-staking-inv-007");
    expect(out).toContain("PROP-vault-inv-001");
    // Sorted by severity by default; Critical row comes first.
    const idxCritical = out.indexOf("PROP-staking-inv-007");
    const idxHigh = out.indexOf("PROP-vault-inv-001");
    expect(idxCritical).toBeGreaterThan(-1);
    expect(idxHigh).toBeGreaterThan(idxCritical);
    // Severity bands present.
    expect(out).toMatch(/CRIT|HIGH|MED|LOW|INFO/);
  });

  it("respects an initial filter passed via --severity", async () => {
    const initial = await loadAll();
    const initialFilter = buildInitialFilter({ severity: "Critical" });
    expect(initialFilter).toBe("severity:Critical");
    const inst = render(
      createElement(FindingBrowser, {
        initial,
        globs: [join(FIXTURES, "04_PARTIAL_*.json")],
        initialFilter,
        nonInteractive: true,
      }),
    );
    created.push(inst);
    const out = strip(inst.lastFrame() ?? "");
    expect(out).toContain("PROP-staking-inv-007");
    expect(out).not.toContain("PROP-vault-pre-002");
    expect(out).toMatch(/1 \/ 6 findings/);
  });

  it("shows a parser error when the initial filter is malformed", async () => {
    const initial = await loadAll();
    const inst = render(
      createElement(FindingBrowser, {
        initial,
        globs: [join(FIXTURES, "04_PARTIAL_*.json")],
        initialFilter: "(severity:High",
        nonInteractive: true,
      }),
    );
    created.push(inst);
    const out = strip(inst.lastFrame() ?? "");
    expect(out).toContain("missing closing paren");
  });

  it("shows the empty state when no findings match", async () => {
    const initial = await loadAll();
    const inst = render(
      createElement(FindingBrowser, {
        initial,
        globs: [join(FIXTURES, "04_PARTIAL_*.json")],
        initialFilter: "severity:Critical AND severity:Low",
        nonInteractive: true,
      }),
    );
    created.push(inst);
    const out = strip(inst.lastFrame() ?? "");
    expect(out).toContain("no findings match");
  });
});
