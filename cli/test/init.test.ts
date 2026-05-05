import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { resolve, join } from "node:path";
import { tmpdir } from "node:os";
import { mkdtempSync } from "node:fs";
import { TargetInfoSchema, BugBountyScopeSchema } from "../src/lib/schemas.js";

describe("TargetInfoSchema", () => {
  it("validates a minimal target info", () => {
    const result = TargetInfoSchema.parse({ target_repo: "org/repo" });
    expect(result.target_repo).toBe("org/repo");
    expect(result.target_commit).toBe("");
    expect(result.target_commit_short).toBe("");
  });

  it("rejects empty target_repo", () => {
    expect(() => TargetInfoSchema.parse({ target_repo: "" })).toThrow();
  });

  it("accepts full target info", () => {
    const result = TargetInfoSchema.parse({
      target_repo: "ethereum/go-ethereum",
      target_commit: "abc1234567890",
      target_commit_short: "abc1234",
      target_ref_label: "main",
      target_ref_type: "branch",
    });
    expect(result.target_repo).toBe("ethereum/go-ethereum");
    expect(result.target_ref_type).toBe("branch");
  });
});

describe("BugBountyScopeSchema", () => {
  it("validates an empty scope (all defaults)", () => {
    const result = BugBountyScopeSchema.parse({});
    expect(result.program_name).toBe("");
    expect(result.in_scope_components).toEqual([]);
    expect(result.out_of_scope_components).toEqual([]);
    expect(result.scope_notes).toEqual([]);
  });

  it("validates a full scope", () => {
    const result = BugBountyScopeSchema.parse({
      program_name: "Ethereum Foundation",
      program_url: "https://immunefi.com/ethereum",
      in_scope_components: ["consensus", "networking"],
      out_of_scope_components: ["docs"],
      scope_notes: ["Only Go code"],
      severity_classification: { critical: "10000 USD" },
    });
    expect(result.program_name).toBe("Ethereum Foundation");
    expect(result.in_scope_components).toHaveLength(2);
    expect(result.severity_classification).toEqual({ critical: "10000 USD" });
  });
});

describe("Schema files match Zod schemas", () => {
  const schemasDir = resolve(__dirname, "..", "..", "schemas");

  it("TargetInfo schema fields align", () => {
    if (!existsSync(join(schemasDir, "TargetInfo.schema.json"))) return;
    const raw = JSON.parse(readFileSync(join(schemasDir, "TargetInfo.schema.json"), "utf8"));
    // Zod schema should accept all fields from JSON Schema
    const fields = Object.keys(raw.properties ?? {});
    const zodShape = TargetInfoSchema.shape;
    for (const field of fields) {
      expect(field in zodShape).toBe(true);
    }
  });

  it("BugBountyScopeInfo schema fields align", () => {
    if (!existsSync(join(schemasDir, "BugBountyScopeInfo.schema.json"))) return;
    const raw = JSON.parse(readFileSync(join(schemasDir, "BugBountyScopeInfo.schema.json"), "utf8"));
    const fields = Object.keys(raw.properties ?? {});
    const zodShape = BugBountyScopeSchema.shape;
    for (const field of fields) {
      expect(field in zodShape).toBe(true);
    }
  });
});
