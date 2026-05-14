/**
 * exportRun — end-to-end: seed an archive, run export, assert the output
 * directory shape + CORPUS_README contents.
 */
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { exportRun } from "../src/lib/corpus/export.js";

const RUN_ID = "2026-05-13T12-00-00Z-abc1234-eip-7825";

let root: string;
let runDir: string;
let outDir: string;

async function seedArchive(): Promise<void> {
  runDir = join(root, RUN_ID);
  await fs.mkdir(join(runDir, "inputs"), { recursive: true });
  await fs.mkdir(join(runDir, "prompts"), { recursive: true });
  await fs.mkdir(join(runDir, "phases", "01a", "partials"), { recursive: true });
  await fs.mkdir(join(runDir, "phases", "01a", "logs"), { recursive: true });
  await fs.mkdir(join(runDir, "phases", "01b", "partials"), { recursive: true });
  await fs.mkdir(join(runDir, "phases", "01b", "graphs", "batch_w0b0_1", "EIP-7825"), { recursive: true });

  await fs.writeFile(
    join(runDir, "manifest.json"),
    JSON.stringify({
      run_id: RUN_ID,
      started_at: "2026-05-13T12:00:00Z",
      ended_at: "2026-05-13T12:02:00Z",
      speca_commit: "abc1234",
      model: { "01a": "claude-sonnet-4-6", "01b": "claude-sonnet-4-6" },
      prompt_shas: { "01a": "deadbeef", "01b": "feedface" },
      spec_sources: ["https://eip.example/7825"],
      phases_completed: ["01a", "01b"],
      cost_usd_total: 0.78,
      notes: "ok",
    }),
    "utf8",
  );
  await fs.writeFile(
    join(runDir, "inputs", "env.json"),
    JSON.stringify({ KEYWORDS: "EIP-7825" }),
    "utf8",
  );
  await fs.writeFile(join(runDir, "prompts", "01a.md"), "# 01a prompt\n", "utf8");
  await fs.writeFile(join(runDir, "prompts", "01b.md"), "# 01b prompt\n", "utf8");
  await fs.writeFile(
    join(runDir, "phases", "01a", "partials", "01a_PARTIAL_W0B0_1.json"),
    JSON.stringify({ items: [] }),
    "utf8",
  );
  await fs.writeFile(
    join(runDir, "phases", "01a", "cost.json"),
    JSON.stringify({ total_cost_usd: 0.16 }),
    "utf8",
  );
  await fs.writeFile(
    join(runDir, "phases", "01a", "logs", "01a_w0b0_1.log.jsonl"),
    [
      JSON.stringify({ type: "assistant", message: { content: [{ type: "text", text: "hi" }] } }),
      "",
    ].join("\n"),
    "utf8",
  );
  await fs.writeFile(
    join(runDir, "phases", "01b", "partials", "01b_PARTIAL_W0B0_2.json"),
    JSON.stringify({ specs: [], metadata: {} }),
    "utf8",
  );
  await fs.writeFile(
    join(runDir, "phases", "01b", "cost.json"),
    JSON.stringify({ total_cost_usd: 0.62 }),
    "utf8",
  );
  await fs.writeFile(
    join(runDir, "phases", "01b", "graphs", "batch_w0b0_1", "EIP-7825", "SG-001.mmd"),
    "stateDiagram-v2\n",
    "utf8",
  );
}

beforeEach(async () => {
  root = await fs.mkdtemp(join(tmpdir(), "speca-corpus-export-"));
  outDir = join(root, "out");
  await seedArchive();
});
afterEach(async () => {
  await fs.rm(root, { recursive: true, force: true });
});

describe("exportRun", () => {
  it("copies prompts/partials/graphs/inputs and writes a filtered manifest", async () => {
    const res = await exportRun({
      runId: RUN_ID,
      outDir,
      includeLogs: false,
      phases: ["01a", "01b"],
      unsafeIncludeFindings: false,
      force: false,
      archiveRootOverride: root,
    });

    expect(res.outDir).toBe(outDir);
    expect(res.phasesExported).toEqual(["01a", "01b"]);

    const exportedManifest = JSON.parse(
      await fs.readFile(join(outDir, "manifest.json"), "utf8"),
    );
    expect(exportedManifest.run_id).toBe(RUN_ID);
    expect(exportedManifest.phases_completed).toEqual(["01a", "01b"]);
    expect(exportedManifest.model).toEqual({
      "01a": "claude-sonnet-4-6",
      "01b": "claude-sonnet-4-6",
    });

    await expect(
      fs.stat(join(outDir, "prompts", "01a.md")),
    ).resolves.toBeDefined();
    await expect(
      fs.stat(join(outDir, "phases", "01a", "partials", "01a_PARTIAL_W0B0_1.json")),
    ).resolves.toBeDefined();
    await expect(
      fs.stat(join(outDir, "phases", "01b", "graphs", "batch_w0b0_1", "EIP-7825", "SG-001.mmd")),
    ).resolves.toBeDefined();
    await expect(
      fs.stat(join(outDir, "phases", "01a", "logs")),
    ).rejects.toBeDefined(); // logs are NOT copied without --include-logs

    const readme = await fs.readFile(join(outDir, "CORPUS_README.md"), "utf8");
    expect(readme).toContain(RUN_ID);
    expect(readme).toContain("01a");
    expect(readme).toContain("01b");
    expect(readme).not.toContain("Logs included");
  });

  it("includes logs when --include-logs is set", async () => {
    const res = await exportRun({
      runId: RUN_ID,
      outDir,
      includeLogs: true,
      phases: ["01a"],
      unsafeIncludeFindings: false,
      force: false,
      archiveRootOverride: root,
    });
    await expect(
      fs.stat(join(outDir, "phases", "01a", "logs", "01a_w0b0_1.log.jsonl")),
    ).resolves.toBeDefined();
    expect(res.redactionStats["01a"]).toBeDefined();
    expect(res.redactionStats["01a"]?.inputLines).toBeGreaterThan(0);
  });

  it("refuses to overwrite an existing --out unless --force", async () => {
    await fs.mkdir(outDir, { recursive: true });
    await expect(
      exportRun({
        runId: RUN_ID,
        outDir,
        includeLogs: false,
        phases: ["01a"],
        unsafeIncludeFindings: false,
        force: false,
        archiveRootOverride: root,
      }),
    ).rejects.toThrow(/already exists/);

    // With --force the export proceeds.
    await exportRun({
      runId: RUN_ID,
      outDir,
      includeLogs: false,
      phases: ["01a"],
      unsafeIncludeFindings: false,
      force: true,
      archiveRootOverride: root,
    });
  });

  it("gates 03/04 phases behind --unsafe-include-findings", async () => {
    await expect(
      exportRun({
        runId: RUN_ID,
        outDir,
        includeLogs: false,
        phases: ["01a", "03"],
        unsafeIncludeFindings: false,
        force: false,
        archiveRootOverride: root,
      }),
    ).rejects.toThrow(/--unsafe-include-findings/);
  });

  it("errors clearly when the run-id is unknown", async () => {
    await expect(
      exportRun({
        runId: "nonexistent-run-id",
        outDir,
        includeLogs: false,
        phases: ["01a"],
        unsafeIncludeFindings: false,
        force: false,
        archiveRootOverride: root,
      }),
    ).rejects.toThrow(/run-id not found/);
  });

  it("strips disallowed keys from inputs/env.json and keeps the allowlist", async () => {
    // Replace the seeded env.json with one that includes a secret.
    await fs.writeFile(
      join(runDir, "inputs", "env.json"),
      JSON.stringify({
        KEYWORDS: "EIP-7825",
        SPEC_URLS: "https://eip.example/7825",
        SPECA_OUTPUT_DIR: "/abs/output",
        SPECA_01A_SCOPE: "primary",
        ORCHESTRATOR_RUNNER: "claude",
        phases: ["01a", "01b"],
        GITHUB_PERSONAL_ACCESS_TOKEN: "ghp_REDACT_ME",
        ANTHROPIC_API_KEY: "sk-ant-REDACT_ME",
        HOMEDIR: "/Users/shieru_k",
      }),
      "utf8",
    );
    await exportRun({
      runId: RUN_ID,
      outDir,
      includeLogs: false,
      phases: ["01a"],
      unsafeIncludeFindings: false,
      force: false,
      archiveRootOverride: root,
    });
    const env = JSON.parse(
      await fs.readFile(join(outDir, "inputs", "env.json"), "utf8"),
    );
    expect(env.KEYWORDS).toBe("EIP-7825");
    expect(env.GITHUB_PERSONAL_ACCESS_TOKEN).toBeUndefined();
    expect(env.ANTHROPIC_API_KEY).toBeUndefined();
    expect(env.HOMEDIR).toBeUndefined();
    expect(env._redacted_keys).toEqual([
      "ANTHROPIC_API_KEY",
      "GITHUB_PERSONAL_ACCESS_TOKEN",
      "HOMEDIR",
    ]);
  });

  it("strips target_info.repo_path from the exported manifest", async () => {
    await fs.writeFile(
      join(runDir, "manifest.json"),
      JSON.stringify({
        run_id: RUN_ID,
        started_at: "2026-05-13T12:00:00Z",
        notes: "ok",
        phases_completed: ["01a"],
        target_info: {
          target_repo: "ethereum/go-ethereum",
          target_commit: "abc1234",
          repo_path: "/Users/shieru_k/Documents/audits/geth",
        },
      }),
      "utf8",
    );
    await exportRun({
      runId: RUN_ID,
      outDir,
      includeLogs: false,
      phases: ["01a"],
      unsafeIncludeFindings: false,
      force: false,
      archiveRootOverride: root,
    });
    const exported = JSON.parse(
      await fs.readFile(join(outDir, "manifest.json"), "utf8"),
    );
    expect(exported.target_info.repo_path).toBeUndefined();
    expect(exported.target_info.target_repo).toBe("ethereum/go-ethereum");
    expect(exported.target_info.target_commit).toBe("abc1234");
  });

  it("truncates a multi-line / long error in notes when rendering the README", async () => {
    const longNotes =
      "error: " +
      "x".repeat(500) +
      "\nTraceback (most recent call last):\n  File \"/secret/path\".py, line 42";
    await fs.writeFile(
      join(runDir, "manifest.json"),
      JSON.stringify({
        run_id: RUN_ID,
        started_at: "2026-05-13T12:00:00Z",
        notes: longNotes,
        phases_completed: ["01a"],
      }),
      "utf8",
    );
    await exportRun({
      runId: RUN_ID,
      outDir,
      includeLogs: false,
      phases: ["01a"],
      unsafeIncludeFindings: false,
      force: false,
      archiveRootOverride: root,
    });
    const readme = await fs.readFile(join(outDir, "CORPUS_README.md"), "utf8");
    expect(readme).not.toContain("Traceback");
    expect(readme).not.toContain("/secret/path");
    // The first line is truncated at 120 chars + ellipsis.
    expect(readme).toMatch(/notes: error: x+…/u);
  });
});
