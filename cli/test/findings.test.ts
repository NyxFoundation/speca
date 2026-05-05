import { describe, it, expect, beforeEach } from "vitest";
import { mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  loadFindings,
  parseFilter,
  applyFilter,
  sortFindings,
  severityRank,
  type Finding,
} from "../src/lib/findings.js";

describe("severityRank", () => {
  it("ranks Critical highest", () => {
    expect(severityRank("Critical")).toBe(4);
    expect(severityRank("High")).toBe(3);
    expect(severityRank("Medium")).toBe(2);
    expect(severityRank("Low")).toBe(1);
    expect(severityRank("Informational")).toBe(0);
  });

  it("returns -1 for unknown", () => {
    expect(severityRank("Unknown")).toBe(-1);
    expect(severityRank("")).toBe(-1);
  });
});

describe("parseFilter", () => {
  it("parses severity filter", () => {
    const f = parseFilter("severity:High");
    expect(f.severity).toBe("High");
  });

  it("parses multiple filters", () => {
    const f = parseFilter("severity:High verdict:Confirmed");
    expect(f.severity).toBe("High");
    expect(f.verdict).toBe("Confirmed");
  });

  it("parses free text", () => {
    const f = parseFilter("overflow buffer");
    expect(f.text).toBe("overflow buffer");
  });

  it("parses mixed filters and text", () => {
    const f = parseFilter("severity:Critical overflow");
    expect(f.severity).toBe("Critical");
    expect(f.text).toBe("overflow");
  });

  it("parses prop filter", () => {
    const f = parseFilter("prop:FN-001");
    expect(f.prop).toBe("FN-001");
  });

  it("returns empty filter for empty string", () => {
    const f = parseFilter("");
    expect(f.severity).toBeUndefined();
    expect(f.text).toBeUndefined();
  });
});

describe("applyFilter", () => {
  const findings: Finding[] = [
    {
      propertyId: "PROP-001",
      checkId: "CHK-001",
      classification: "Buffer Overflow",
      severity: "Critical",
      verdict: "Confirmed",
      summary: "Stack buffer overflow in parser",
      reviewerNotes: "",
      finalRecommendation: "",
      codePath: "src/parser.c",
      codeSnippet: "",
      sourceFile: "04_PARTIAL_W1B1.json",
    },
    {
      propertyId: "PROP-002",
      checkId: "CHK-002",
      classification: "Integer Overflow",
      severity: "Medium",
      verdict: "Disputed",
      summary: "Integer overflow in fee calculation",
      reviewerNotes: "",
      finalRecommendation: "",
      codePath: "src/fees.go",
      codeSnippet: "",
      sourceFile: "04_PARTIAL_W1B2.json",
    },
    {
      propertyId: "PROP-003",
      checkId: "CHK-003",
      classification: "Access Control",
      severity: "High",
      verdict: "Confirmed",
      summary: "Missing auth check on admin endpoint",
      reviewerNotes: "",
      finalRecommendation: "",
      codePath: "src/api/admin.go",
      codeSnippet: "",
      sourceFile: "04_PARTIAL_W2B1.json",
    },
  ];

  it("filters by severity", () => {
    const result = applyFilter(findings, { severity: "Critical" });
    expect(result).toHaveLength(1);
    expect(result[0]!.propertyId).toBe("PROP-001");
  });

  it("filters by verdict", () => {
    const result = applyFilter(findings, { verdict: "Confirmed" });
    expect(result).toHaveLength(2);
  });

  it("filters by free text", () => {
    const result = applyFilter(findings, { text: "overflow" });
    expect(result).toHaveLength(2);
  });

  it("combines filters with AND", () => {
    const result = applyFilter(findings, { severity: "Critical", text: "overflow" });
    expect(result).toHaveLength(1);
  });

  it("filters by prop", () => {
    const result = applyFilter(findings, { prop: "PROP-002" });
    expect(result).toHaveLength(1);
  });

  it("returns all when no filter", () => {
    const result = applyFilter(findings, {});
    expect(result).toHaveLength(3);
  });
});

describe("sortFindings", () => {
  it("sorts by severity descending", () => {
    const findings: Finding[] = [
      { propertyId: "A", severity: "Low" } as Finding,
      { propertyId: "B", severity: "Critical" } as Finding,
      { propertyId: "C", severity: "Medium" } as Finding,
    ];
    const sorted = sortFindings(findings);
    expect(sorted[0]!.propertyId).toBe("B");
    expect(sorted[1]!.propertyId).toBe("C");
    expect(sorted[2]!.propertyId).toBe("A");
  });

  it("sorts by propertyId when same severity", () => {
    const findings: Finding[] = [
      { propertyId: "B", severity: "High" } as Finding,
      { propertyId: "A", severity: "High" } as Finding,
    ];
    const sorted = sortFindings(findings);
    expect(sorted[0]!.propertyId).toBe("A");
    expect(sorted[1]!.propertyId).toBe("B");
  });
});

describe("loadFindings", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "speca-findings-"));
  });

  it("loads Phase 04 partial files", async () => {
    const partial = {
      reviewed_items: [
        {
          property_id: "PROP-001",
          check_id: "CHK-001",
          original_finding: { classification: "XSS", summary: "Reflected XSS" },
          review_verdict: "Confirmed",
          adjusted_severity: "High",
          reviewer_notes: "Verified",
          final_recommendation: "Fix input sanitization",
        },
      ],
      source_files: [],
    };
    writeFileSync(join(tmpDir, "04_PARTIAL_W1B1_20260101.json"), JSON.stringify(partial));

    const findings = await loadFindings(tmpDir);
    expect(findings).toHaveLength(1);
    expect(findings[0]!.propertyId).toBe("PROP-001");
    expect(findings[0]!.severity).toBe("High");
    expect(findings[0]!.verdict).toBe("Confirmed");
  });

  it("falls back to Phase 03 when no Phase 04 files", async () => {
    const partial = {
      audit_items: [
        {
          property_id: "PROP-002",
          check_id: "CHK-002",
          classification: "SQL Injection",
          summary: "Unparameterized query",
          code_path: "src/db.py",
        },
      ],
    };
    writeFileSync(join(tmpDir, "03_PARTIAL_W1B1_20260101.json"), JSON.stringify(partial));

    const findings = await loadFindings(tmpDir);
    expect(findings).toHaveLength(1);
    expect(findings[0]!.propertyId).toBe("PROP-002");
    expect(findings[0]!.codePath).toBe("src/db.py");
  });

  it("returns empty array for empty directory", async () => {
    const findings = await loadFindings(tmpDir);
    expect(findings).toEqual([]);
  });

  it("skips malformed JSON files", async () => {
    writeFileSync(join(tmpDir, "04_PARTIAL_bad.json"), "not json{{{");
    const findings = await loadFindings(tmpDir);
    expect(findings).toEqual([]);
  });
});
