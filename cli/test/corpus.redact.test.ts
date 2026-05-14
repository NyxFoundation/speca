/**
 * Stream-JSON log redactor — line-by-line policy enforcement.
 */
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { redactLinesForTest } from "../src/lib/corpus/redact.js";

const TARGET_ROOT = resolve("/abs/target-repo");

function toolUse(name: string, input: Record<string, unknown>): string {
  return JSON.stringify({
    type: "assistant",
    message: { content: [{ type: "tool_use", name, input }] },
  });
}

describe("redactLinesForTest", () => {
  it("drops Read tool_use whose file_path resolves under repo_path", () => {
    const lines = [
      toolUse("Read", { file_path: resolve(TARGET_ROOT, "src/foo.go") }),
    ];
    const { kept, stats } = redactLinesForTest(lines, {
      targetRepoPath: TARGET_ROOT,
    });
    expect(kept).toHaveLength(0);
    expect(stats.droppedToolUseByPath).toBe(1);
  });

  it("keeps Read whose file_path is outside the repo_path", () => {
    const lines = [toolUse("Read", { file_path: "/abs/elsewhere/x.txt" })];
    const { kept, stats } = redactLinesForTest(lines, {
      targetRepoPath: TARGET_ROOT,
    });
    expect(kept).toHaveLength(1);
    expect(stats.droppedToolUseByPath).toBe(0);
  });

  it("keeps mcp__* tool_use even when path-like input is under repo_path", () => {
    const lines = [
      toolUse("mcp__tree_sitter__get_symbols", {
        path: resolve(TARGET_ROOT, "src/foo.go"),
      }),
    ];
    const { kept } = redactLinesForTest(lines, { targetRepoPath: TARGET_ROOT });
    expect(kept).toHaveLength(1);
  });

  it("keeps Write tool_use even when file_path is under repo_path", () => {
    const lines = [
      toolUse("Write", { file_path: resolve(TARGET_ROOT, "outputs/x.json") }),
    ];
    const { kept } = redactLinesForTest(lines, { targetRepoPath: TARGET_ROOT });
    expect(kept).toHaveLength(1);
  });

  it("disables path filtering and counts when targetRepoPath is null", () => {
    const lines = [
      toolUse("Grep", { pattern: "TODO", path: resolve("/anywhere/x.go") }),
      toolUse("Read", { file_path: resolve("/anywhere/y.go") }),
    ];
    const { kept, stats } = redactLinesForTest(lines, { targetRepoPath: null });
    expect(kept).toHaveLength(2);
    expect(stats.droppedToolUseByPath).toBe(0);
    expect(stats.unfilteredReadGrepGlob).toBe(2);
  });

  it("matches path with mixed separators (POSIX-style path under Windows-style root)", () => {
    // Simulate a tool_use whose file_path was emitted by the orchestrator
    // in POSIX form on a Windows host (Node's `path.resolve` normalises to
    // the host's native sep; we rely on `path.relative` for matching). The
    // pre-fix version did a `startsWith` against `repoRoot + "\\"` and
    // `repoRoot + "/"` separately, missing this case.
    const repoRoot = resolve("/abs/target-repo");
    const childPath = resolve(repoRoot, "src/deep/file.go");
    const lines = [toolUse("Read", { file_path: childPath })];
    const { kept } = redactLinesForTest(lines, { targetRepoPath: repoRoot });
    expect(kept).toHaveLength(0);
  });

  it("keeps sibling-dir paths that share the repo prefix but live outside it", () => {
    // Classic prefix-vulnerable check: `/abs/target-repo` vs
    // `/abs/target-repo-other`. Old implementation could match the latter
    // because it tested `"/abs/target-repo-other"`.startsWith("/abs/target-repo").
    const lines = [
      toolUse("Read", { file_path: resolve("/abs/target-repo-other/file.go") }),
    ];
    const { kept } = redactLinesForTest(lines, {
      targetRepoPath: resolve("/abs/target-repo"),
    });
    expect(kept).toHaveLength(1);
  });

  it("default-keeps non-tool-use lines (assistant text, etc.)", () => {
    const lines = [
      JSON.stringify({ type: "assistant", message: { content: [{ type: "text", text: "hi" }] } }),
      JSON.stringify({ type: "user", message: { content: [] } }),
    ];
    const { kept } = redactLinesForTest(lines, { targetRepoPath: TARGET_ROOT });
    expect(kept).toHaveLength(2);
  });

  it("default-keeps malformed lines but counts them", () => {
    const lines = ["not json", JSON.stringify({ type: "assistant" })];
    const { kept, stats } = redactLinesForTest(lines, {
      targetRepoPath: TARGET_ROOT,
    });
    expect(kept).toHaveLength(2);
    expect(stats.malformedLines).toBe(1);
  });

  it("preserves blank lines", () => {
    const lines = ["", " ", JSON.stringify({ type: "assistant" })];
    const { kept } = redactLinesForTest(lines, { targetRepoPath: TARGET_ROOT });
    expect(kept).toHaveLength(3);
  });
});
