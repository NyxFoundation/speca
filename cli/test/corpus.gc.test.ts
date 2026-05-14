/**
 * gcRuns — age cutoff filtering + soft-delete semantics.
 */
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { gcRuns } from "../src/lib/corpus/gc.js";

let root: string;
beforeEach(async () => {
  root = await fs.mkdtemp(join(tmpdir(), "speca-corpus-gc-"));
});
afterEach(async () => {
  await fs.rm(root, { recursive: true, force: true });
});

async function seedRun(runId: string, startedAt: string): Promise<void> {
  const dir = join(root, runId);
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(
    join(dir, "manifest.json"),
    JSON.stringify({ run_id: runId, started_at: startedAt, notes: "ok" }),
    "utf8",
  );
}

describe("gcRuns", () => {
  it("dry-run reports candidates but does not move anything", async () => {
    await seedRun("2024-01-01T00-00-00Z-abc-old", "2024-01-01T00:00:00Z");
    await seedRun("2026-05-13T12-00-00Z-abc-new", "2026-05-13T12:00:00Z");
    const now = Date.parse("2026-05-13T13:00:00Z");
    const res = await gcRuns({
      root,
      olderThanMs: 90 * 86_400_000,
      dryRun: true,
      now,
    });
    expect(res.candidates).toHaveLength(1);
    expect(res.candidates[0]?.action).toBe("would-delete");
    expect(res.candidates[0]?.row.runId).toContain("old");

    // Still on disk after a dry-run.
    const oldDir = join(root, "2024-01-01T00-00-00Z-abc-old");
    await expect(fs.stat(oldDir)).resolves.toBeDefined();
  });

  it("real run moves expired archives into .trash/", async () => {
    await seedRun("2024-01-01T00-00-00Z-abc-old", "2024-01-01T00:00:00Z");
    const now = Date.parse("2026-05-13T13:00:00Z");
    const res = await gcRuns({
      root,
      olderThanMs: 90 * 86_400_000,
      dryRun: false,
      now,
    });
    expect(res.candidates[0]?.action).toBe("deleted");
    await expect(
      fs.stat(join(root, "2024-01-01T00-00-00Z-abc-old")),
    ).rejects.toBeDefined();
    const trashEntries = await fs.readdir(join(root, ".trash"));
    expect(trashEntries).toHaveLength(1);
  });

  it("skips when started_at is unreadable and run-id timestamp is unparseable", async () => {
    const dir = join(root, "not-a-runid-format");
    await fs.mkdir(dir, { recursive: true });
    await fs.writeFile(join(dir, "manifest.json"), "corrupt", "utf8");
    const res = await gcRuns({
      root,
      olderThanMs: 1,
      dryRun: false,
      now: Date.now(),
    });
    // run-id doesn't match the YYYY-MM-DDTHH-MM-SSZ pattern, so age can't be
    // resolved → skip is reported, no deletion occurred.
    expect(res.candidates.some((c) => c.action === "skipped")).toBe(true);
    await expect(fs.stat(dir)).resolves.toBeDefined();
  });

  it("falls back to run-id timestamp when manifest is missing", async () => {
    const dir = join(root, "2024-01-01T00-00-00Z-abc-no-manifest");
    await fs.mkdir(dir, { recursive: true });
    // No manifest.json at all — listRuns reports as unreadable, gc should
    // still find the age from the run-id.
    const now = Date.parse("2026-05-13T13:00:00Z");
    const res = await gcRuns({
      root,
      olderThanMs: 90 * 86_400_000,
      dryRun: true,
      now,
    });
    expect(res.candidates[0]?.action).toBe("would-delete");
  });

  it("returns an empty candidate list when nothing is old enough", async () => {
    await seedRun("2026-05-13T12-00-00Z-abc-fresh", "2026-05-13T12:00:00Z");
    const now = Date.parse("2026-05-13T13:00:00Z");
    const res = await gcRuns({
      root,
      olderThanMs: 90 * 86_400_000,
      dryRun: true,
      now,
    });
    expect(res.candidates).toHaveLength(0);
  });

  it("uses dryRun=true as the safe default when opts.dryRun is omitted", async () => {
    await seedRun("2024-01-01T00-00-00Z-abc-old", "2024-01-01T00:00:00Z");
    const now = Date.parse("2026-05-13T13:00:00Z");
    const res = await gcRuns({ root, olderThanMs: 1, now });
    expect(res.candidates[0]?.action).toBe("would-delete");
    // Archive untouched because no explicit dryRun: false.
    await expect(
      fs.stat(join(root, "2024-01-01T00-00-00Z-abc-old")),
    ).resolves.toBeDefined();
  });

  it("produces unique trash paths for multiple candidates in one call", async () => {
    await seedRun("2024-01-01T00-00-00Z-abc-old1", "2024-01-01T00:00:00Z");
    await seedRun("2024-01-02T00-00-00Z-abc-old2", "2024-01-02T00:00:00Z");
    const now = Date.parse("2026-05-13T13:00:00Z");
    const res = await gcRuns({
      root,
      olderThanMs: 1,
      dryRun: false,
      now,
    });
    expect(res.candidates.filter((c) => c.action === "deleted")).toHaveLength(2);
    const trashEntries = await fs.readdir(join(root, ".trash"));
    expect(trashEntries).toHaveLength(2);
    // Different trash names — the nonce should prevent collision.
    expect(new Set(trashEntries).size).toBe(2);
  });
});
