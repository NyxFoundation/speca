/**
 * listRuns — discovery + sort + tolerant of bad archives.
 */
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { listRuns } from "../src/lib/corpus/runs.js";

let root: string;
beforeEach(async () => {
  root = await fs.mkdtemp(join(tmpdir(), "speca-corpus-runs-"));
});
afterEach(async () => {
  await fs.rm(root, { recursive: true, force: true });
});

async function seedRun(
  runId: string,
  manifest: Record<string, unknown>,
): Promise<void> {
  const dir = join(root, runId);
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(join(dir, "manifest.json"), JSON.stringify(manifest), "utf8");
}

describe("listRuns", () => {
  it("returns [] when archive root does not exist", async () => {
    await fs.rm(root, { recursive: true, force: true });
    expect(await listRuns(root)).toEqual([]);
  });

  it("returns [] when archive root is empty", async () => {
    expect(await listRuns(root)).toEqual([]);
  });

  it("returns one row per readable manifest sorted desc by startedAt", async () => {
    await seedRun("2026-05-13T12-00-00Z-abc-eip-7825", {
      run_id: "2026-05-13T12-00-00Z-abc-eip-7825",
      started_at: "2026-05-13T12:00:00Z",
      notes: "ok",
      phases_completed: ["01a", "01b"],
      cost_usd_total: 0.4,
    });
    await seedRun("2026-05-13T11-00-00Z-abc-eip-7951", {
      run_id: "2026-05-13T11-00-00Z-abc-eip-7951",
      started_at: "2026-05-13T11:00:00Z",
      notes: "ok",
      phases_completed: ["01a", "01b", "01e"],
      cost_usd_total: 0.94,
    });
    const rows = await listRuns(root);
    expect(rows.map((r) => r.runId)).toEqual([
      "2026-05-13T12-00-00Z-abc-eip-7825",
      "2026-05-13T11-00-00Z-abc-eip-7951",
    ]);
    expect(rows[0]?.status).toBe("ok");
    expect(rows[0]?.phasesCompleted).toEqual(["01a", "01b"]);
  });

  it("marks unreadable rows and floats them to the bottom", async () => {
    await seedRun("2026-05-13T12-00-00Z-abc-eip-7825", {
      run_id: "2026-05-13T12-00-00Z-abc-eip-7825",
      started_at: "2026-05-13T12:00:00Z",
    });
    const corruptDir = join(root, "2026-05-13T11-00-00Z-zzz-corrupt");
    await fs.mkdir(corruptDir, { recursive: true });
    await fs.writeFile(join(corruptDir, "manifest.json"), "not json", "utf8");
    const rows = await listRuns(root);
    expect(rows).toHaveLength(2);
    expect(rows[0]?.unreadable).toBe(false);
    expect(rows[1]?.unreadable).toBe(true);
    expect(rows[1]?.unreadableReason).toBeTruthy();
  });

  it("skips non-directory entries in the archive root", async () => {
    await fs.writeFile(join(root, "not-a-run.txt"), "ignore me");
    await seedRun("2026-05-13T12-00-00Z-abc-eip-7825", {
      run_id: "2026-05-13T12-00-00Z-abc-eip-7825",
      started_at: "2026-05-13T12:00:00Z",
    });
    const rows = await listRuns(root);
    expect(rows).toHaveLength(1);
  });

  it("skips dot-directories (e.g. .trash/)", async () => {
    await fs.mkdir(join(root, ".trash"), { recursive: true });
    await seedRun("2026-05-13T12-00-00Z-abc-eip-7825", {
      run_id: "2026-05-13T12-00-00Z-abc-eip-7825",
      started_at: "2026-05-13T12:00:00Z",
    });
    const rows = await listRuns(root);
    expect(rows.map((r) => r.runId)).toEqual([
      "2026-05-13T12-00-00Z-abc-eip-7825",
    ]);
  });
});
