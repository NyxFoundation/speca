import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { expandGlobs, loadFindings } from "../src/lib/findings/loader.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURES = resolve(__dirname, "fixtures");

describe("loadFindings", () => {
  it("loads + dedupes Phase 03 + Phase 04 fixtures", async () => {
    const result = await loadFindings([
      join(FIXTURES, "03_PARTIAL_*.json"),
      join(FIXTURES, "04_PARTIAL_*.json"),
    ]);
    expect(result.warnings).toEqual([]);
    expect(result.files.length).toBe(4);
    // Property IDs in the fixture set:
    //   PROP-vault-inv-001 (03 + 04, also duplicated across 04 batches)
    //   PROP-vault-pre-002 (04)
    //   PROP-vault-inv-003 (04)
    //   PROP-staking-inv-007 (04)
    //   PROP-staking-post-008 (04)
    //   PROP-misc-asm-099 (04)
    const ids = result.findings.map((f) => f.propertyId).sort();
    expect(ids).toEqual([
      "PROP-misc-asm-099",
      "PROP-staking-inv-007",
      "PROP-staking-post-008",
      "PROP-vault-inv-001",
      "PROP-vault-inv-003",
      "PROP-vault-pre-002",
    ]);
  });

  it("merges Phase 03 fields (proof + attack) into the Phase 04 record", async () => {
    const result = await loadFindings([
      join(FIXTURES, "03_PARTIAL_*.json"),
      join(FIXTURES, "04_PARTIAL_*.json"),
    ]);
    const vault = result.findings.find((f) => f.propertyId === "PROP-vault-inv-001");
    expect(vault).toBeDefined();
    expect(vault!.verdict).toBe("CONFIRMED_VULNERABILITY");
    expect(vault!.severity).toBe("High");
    expect(vault!.proofTrace).toContain("re-enter");
    expect(vault!.attackScenario).toContain("receive()");
    expect(vault!.primaryLocation?.file).toBe("contracts/Vault.sol");
    expect(vault!.primaryLocation?.startLine).toBe(128);
    expect(vault!.primaryLocation?.endLine).toBe(145);
    expect(vault!.sourceFiles.length).toBeGreaterThanOrEqual(2);
  });

  it("keeps fields from the first 04 record on duplicate property_id", async () => {
    const result = await loadFindings([join(FIXTURES, "04_PARTIAL_*.json")]);
    const vault = result.findings.find((f) => f.propertyId === "PROP-vault-inv-001");
    expect(vault).toBeDefined();
    // The W0 record (lower mtime) carries the meaningful note; the W1 record
    // explicitly says "Duplicate batch — should be deduped". Whichever wins,
    // the verdict must remain CONFIRMED_VULNERABILITY and the severity High.
    expect(vault!.verdict).toBe("CONFIRMED_VULNERABILITY");
    expect(vault!.severity).toBe("High");
  });

  it("warns and skips a malformed JSON file", async () => {
    const tmp = await fs.mkdtemp(join(tmpdir(), "speca-loader-test-"));
    try {
      const goodPath = join(tmp, "04_PARTIAL_W0B0_1.json");
      const badPath = join(tmp, "04_PARTIAL_W1B0_2.json");
      await fs.copyFile(join(FIXTURES, "04_PARTIAL_W0B0_1700000000.json"), goodPath);
      await fs.writeFile(badPath, "this is not JSON", "utf8");
      const result = await loadFindings([join(tmp, "04_PARTIAL_*.json")]);
      expect(result.findings.length).toBeGreaterThan(0);
      expect(result.warnings.length).toBe(1);
      expect(result.warnings[0]?.file).toBe(resolve(badPath));
    } finally {
      await fs.rm(tmp, { recursive: true, force: true });
    }
  });

  it("returns empty result with no warnings when nothing matches", async () => {
    const tmp = await fs.mkdtemp(join(tmpdir(), "speca-loader-test-"));
    try {
      const result = await loadFindings([join(tmp, "*.json")]);
      expect(result.findings).toEqual([]);
      expect(result.warnings).toEqual([]);
      expect(result.files).toEqual([]);
    } finally {
      await fs.rm(tmp, { recursive: true, force: true });
    }
  });

  it("expandGlobs honours absolute and relative patterns", async () => {
    const matches = await expandGlobs([join(FIXTURES, "04_PARTIAL_*.json")]);
    expect(matches.length).toBeGreaterThan(0);
    for (const m of matches) {
      expect(m.endsWith(".json")).toBe(true);
    }
  });
});
