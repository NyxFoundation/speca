import { describe, expect, it } from "vitest";
import {
  formatErrors,
  validateBugBountyScope,
  validateTargetInfo,
} from "../src/lib/schemas/index.js";

describe("validateTargetInfo", () => {
  it("accepts a minimal valid TargetInfo", () => {
    const result = validateTargetInfo({ target_repo: "https://github.com/foo/bar" });
    expect(result.ok).toBe(true);
  });

  it("accepts a fully populated TargetInfo with extra wizard fields", () => {
    const result = validateTargetInfo({
      target_repo: "https://github.com/sigp/lighthouse",
      target_ref_type: "head",
      target_ref_label: "HEAD",
      target_commit: "",
      target_commit_short: "",
      project_name: "lighthouse",
      target_language: "Rust",
      target_layer: "consensus",
    });
    expect(result.ok).toBe(true);
  });

  it("rejects a TargetInfo missing target_repo", () => {
    const result = validateTargetInfo({ target_ref_label: "HEAD" });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(formatErrors(result.errors)).toMatch(/target_repo/);
    }
  });

  it("rejects a TargetInfo with wrong type for target_repo", () => {
    const result = validateTargetInfo({ target_repo: 42 });
    expect(result.ok).toBe(false);
  });

  it("rejects a non-object payload", () => {
    const result = validateTargetInfo("not-an-object");
    expect(result.ok).toBe(false);
  });
});

describe("validateBugBountyScope", () => {
  it("accepts an empty BugBountyScope (all fields optional)", () => {
    const result = validateBugBountyScope({});
    expect(result.ok).toBe(true);
  });

  it("accepts a fully populated BugBountyScope", () => {
    const result = validateBugBountyScope({
      program_name: "ethereum.org",
      program_url: "https://ethereum.org/en/bug-bounty/",
      inherited_from: "ethereum.org",
      in_scope_components: ["geth", "lighthouse"],
      out_of_scope_components: ["typos"],
      scope_notes: ["see source"],
      severity_classification: {
        Critical: { criteria: "...", impact: "..." },
      },
    });
    expect(result.ok).toBe(true);
  });

  it("rejects when in_scope_components is the wrong type", () => {
    const result = validateBugBountyScope({
      in_scope_components: "not-an-array",
    });
    expect(result.ok).toBe(false);
  });

  it("rejects when severity_classification is the wrong type", () => {
    const result = validateBugBountyScope({
      severity_classification: ["should be object"],
    });
    expect(result.ok).toBe(false);
  });
});
