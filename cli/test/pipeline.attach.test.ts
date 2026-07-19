import { mkdirSync, mkdtempSync, rmSync, utimesSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  ATTACH_ACTIVE_WINDOW_MS,
  buildAttachSnapshot,
  parsePartialFilename,
  scanAttachState,
  seedPhaseStatus,
  type AttachPhaseSeed,
} from "../src/lib/pipeline/attach.js";

let cwd: string;
beforeEach(() => {
  cwd = mkdtempSync(join(tmpdir(), "speca-attach-"));
});
afterEach(() => {
  rmSync(cwd, { recursive: true, force: true });
});

function writePartial(dir: string, name: string, items: number, ageMs = 0): string {
  const path = join(dir, name);
  const list = Array.from({ length: items }, (_, i) => ({ property_id: `PROP-x-${i}` }));
  writeFileSync(
    path,
    JSON.stringify({
      reviewed_items: list,
      metadata: { phase: "04", worker_id: 0, batch_index: 0, item_count: items },
    }),
  );
  if (ageMs > 0) {
    const t = (Date.now() - ageMs) / 1000;
    utimesSync(path, t, t);
  }
  return path;
}

describe("parsePartialFilename", () => {
  it("parses the canonical {phase}_PARTIAL_W{w}B{b}_{ts}.json pattern", () => {
    expect(parsePartialFilename("04_PARTIAL_W2B13_1700000000.json")).toEqual({
      phase: "04",
      worker: "2",
      batch: "13",
      ts: "1700000000",
    });
    expect(parsePartialFilename("01b_PARTIAL_W0B0_1700000000.json")?.phase).toBe("01b");
  });

  it("accepts legacy names without a timestamp suffix", () => {
    expect(parsePartialFilename("01b_PARTIAL_W0B0.json")).toEqual({
      phase: "01b",
      worker: "0",
      batch: "0",
      ts: "",
    });
  });

  it("rejects STATE / CONTEXT / QUEUE / ASYNC_QUEUE and unrelated files", () => {
    expect(parsePartialFilename("01a_STATE.json")).toBeNull();
    expect(parsePartialFilename("04_CONTEXT_W0B0_1700000000.json")).toBeNull();
    expect(parsePartialFilename("04_ASYNC_QUEUE_W0B0_1700000000.json")).toBeNull();
    expect(parsePartialFilename("03_QUEUE_0.json")).toBeNull();
    expect(parsePartialFilename("TARGET_INFO.json")).toBeNull();
    expect(parsePartialFilename("garbage.txt")).toBeNull();
  });
});

describe("scanAttachState", () => {
  it("returns detected=false when outputs/ does not exist", async () => {
    const scan = await scanAttachState({ cwd });
    expect(scan.detected).toBe(false);
    expect(scan.phases).toEqual([]);
    expect(scan.latestActivityMs).toBe(0);
  });

  it("returns detected=false when outputs/ has no PARTIAL or log files", async () => {
    const outputs = join(cwd, "outputs");
    mkdirSync(outputs, { recursive: true });
    writeFileSync(join(outputs, "TARGET_INFO.json"), "{}");
    const scan = await scanAttachState({ cwd });
    expect(scan.detected).toBe(false);
  });

  it("aggregates phases, workers, batches and item counts from PARTIALs", async () => {
    const outputs = join(cwd, "outputs");
    mkdirSync(outputs, { recursive: true });
    writePartial(outputs, "04_PARTIAL_W0B0_1700000000.json", 3);
    writePartial(outputs, "04_PARTIAL_W1B1_1700000010.json", 2);
    writePartial(outputs, "01b_PARTIAL_W0B0_1699000000.json", 1);

    const scan = await scanAttachState({ cwd });
    expect(scan.detected).toBe(true);
    expect(scan.phases.map((p) => p.id)).toEqual(["01b", "04"]);
    const p04 = scan.phases.find((p) => p.id === "04")!;
    expect(p04.partialBatches).toBe(2);
    expect(p04.items).toBe(5);
    expect(p04.workers).toEqual(["0", "1"]);
  });

  it("merges worker ids observed only in outputs/logs/", async () => {
    const outputs = join(cwd, "outputs");
    const logs = join(outputs, "logs");
    mkdirSync(logs, { recursive: true });
    writePartial(outputs, "03_PARTIAL_W0B0_1700000000.json", 1);
    writeFileSync(join(logs, "03_w4b9_1700000123.log.jsonl"), '{"type":"system"}\n');

    const scan = await scanAttachState({ cwd });
    const p03 = scan.phases.find((p) => p.id === "03")!;
    expect(p03.workers).toEqual(["0", "4"]);
    // Log-only activity still counts toward the phase's freshness.
    expect(p03.lastActivityMs).toBeGreaterThan(0);
  });

  it("honours an explicit outputDir override", async () => {
    const custom = join(cwd, "elsewhere");
    mkdirSync(custom, { recursive: true });
    writePartial(custom, "04_PARTIAL_W0B0_1700000000.json", 1);
    const scan = await scanAttachState({ cwd, outputDir: "elsewhere" });
    expect(scan.detected).toBe(true);
    expect(scan.outputsDir).toBe(custom);
  });

  it("counts array lengths when metadata.item_count is missing", async () => {
    const outputs = join(cwd, "outputs");
    mkdirSync(outputs, { recursive: true });
    writeFileSync(
      join(outputs, "03_PARTIAL_W0B0_1700000000.json"),
      JSON.stringify({ audit_items: [{ property_id: "a" }, { property_id: "b" }] }),
    );
    const scan = await scanAttachState({ cwd });
    expect(scan.phases[0]?.items).toBe(2);
  });

  it("treats an unparseable PARTIAL as zero items, not an error", async () => {
    const outputs = join(cwd, "outputs");
    mkdirSync(outputs, { recursive: true });
    writeFileSync(join(outputs, "04_PARTIAL_W0B0_1700000000.json"), "{ not json");
    const scan = await scanAttachState({ cwd });
    expect(scan.detected).toBe(true);
    expect(scan.phases[0]?.items).toBe(0);
  });
});

describe("seedPhaseStatus / buildAttachSnapshot", () => {
  const seed = (overrides: Partial<AttachPhaseSeed>): AttachPhaseSeed => ({
    id: "04",
    workers: ["0"],
    partialBatches: 1,
    items: 1,
    lastActivityMs: 0,
    firstActivityMs: 0,
    ...overrides,
  });

  it("marks recent activity as running and stale activity as done", () => {
    const now = Date.now();
    expect(seedPhaseStatus(seed({ lastActivityMs: now - 1_000 }), now)).toBe("running");
    expect(seedPhaseStatus(seed({ lastActivityMs: now - ATTACH_ACTIVE_WINDOW_MS - 1 }), now)).toBe("done");
  });

  it("builds a snapshot with phase order, statuses and real item counts", async () => {
    const outputs = join(cwd, "outputs");
    mkdirSync(outputs, { recursive: true });
    writePartial(outputs, "01b_PARTIAL_W0B0_1699000000.json", 4, 60 * 60 * 1000);
    writePartial(outputs, "04_PARTIAL_W0B0_1700000000.json", 3);
    writePartial(outputs, "04_PARTIAL_W1B1_1700000010.json", 2);

    const scan = await scanAttachState({ cwd });
    const snap = buildAttachSnapshot(scan, Date.now());

    expect(snap.phaseOrder).toEqual(["01b", "04"]);
    expect(snap.phases.get("01b")?.status).toBe("done");
    expect(snap.phases.get("01b")?.totalResults).toBe(4);
    expect(snap.phases.get("04")?.status).toBe("running");
    expect(snap.phases.get("04")?.totalResults).toBe(5);
    expect(snap.phases.get("04")?.batchesObserved).toBe(2);
    expect(Object.keys(snap.phases.get("04")?.workerActivity ?? {})).toEqual(["W0", "W1"]);
    expect(snap.pipelineStatus).toBe("running");
    expect(snap.startedAt).toBeDefined();
  });

  it("reports idle (not completed/failed) when every phase has gone quiet", async () => {
    const outputs = join(cwd, "outputs");
    mkdirSync(outputs, { recursive: true });
    writePartial(outputs, "04_PARTIAL_W0B0_1700000000.json", 1, 60 * 60 * 1000);
    const scan = await scanAttachState({ cwd });
    const snap = buildAttachSnapshot(scan, Date.now());
    expect(snap.pipelineStatus).toBe("idle");
    expect(snap.phases.get("04")?.status).toBe("done");
  });
});
