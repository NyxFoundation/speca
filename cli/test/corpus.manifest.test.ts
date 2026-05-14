/**
 * Manifest reader — zod schema tolerance, status derivation, summarise.
 */
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  deriveStatus,
  readManifest,
  runManifestSchema,
  summarise,
} from "../src/lib/corpus/manifest.js";

let dir: string;
beforeEach(async () => {
  dir = await fs.mkdtemp(join(tmpdir(), "speca-corpus-manifest-"));
});
afterEach(async () => {
  await fs.rm(dir, { recursive: true, force: true });
});

describe("runManifestSchema", () => {
  it("accepts a minimal manifest and fills defaults", () => {
    const out = runManifestSchema.parse({
      run_id: "x",
      started_at: "2026-05-13T12:00:00Z",
    });
    expect(out.run_id).toBe("x");
    expect(out.spec_sources).toEqual([]);
    expect(out.phases_completed).toEqual([]);
    expect(out.cost_usd_total).toBe(0);
    expect(out.speca_commit).toBe("");
  });

  it("accepts a fully populated manifest", () => {
    const raw = {
      run_id: "2026-05-13T12-00-00Z-abc1234-eip-7825",
      started_at: "2026-05-13T12:00:00Z",
      ended_at: "2026-05-13T12:02:00Z",
      speca_commit: "deadbee",
      cli_version: "0.9.1",
      model: { "01a": "claude-sonnet-4-6" },
      prompt_shas: { "01a": "abc123" },
      spec_sources: ["https://eip.example/7825"],
      target_info: null,
      bug_bounty_scope_sha: null,
      phases_completed: ["01a"],
      cost_usd_total: 0.16,
      notes: "ok",
    };
    expect(() => runManifestSchema.parse(raw)).not.toThrow();
  });

  it("tolerates extra fields", () => {
    const out = runManifestSchema.parse({
      run_id: "x",
      started_at: "2026-05-13T12:00:00Z",
      future_field: "anything",
    });
    expect(out["future_field" as keyof typeof out]).toBe("anything");
  });

  it("rejects missing run_id", () => {
    expect(() =>
      runManifestSchema.parse({ started_at: "2026-05-13T12:00:00Z" }),
    ).toThrow();
  });
});

describe("deriveStatus", () => {
  it("returns ok when notes === 'ok'", () => {
    expect(deriveStatus({ notes: "ok", ended_at: "2026-05-13T12:00:00Z" })).toBe(
      "ok",
    );
  });
  it("returns error when notes starts with 'error'", () => {
    expect(
      deriveStatus({ notes: "error: phase 03 failed", ended_at: "x" }),
    ).toBe("error");
  });
  it("returns pending when ended_at is missing and notes empty", () => {
    expect(deriveStatus({ notes: null, ended_at: null })).toBe("pending");
  });
  it("returns unknown when notes is empty but ended_at exists", () => {
    expect(deriveStatus({ notes: null, ended_at: "x" })).toBe("unknown");
  });
});

describe("summarise", () => {
  it("extracts target_repo from target_info when present", () => {
    const m = runManifestSchema.parse({
      run_id: "x",
      started_at: "2026-05-13T12:00:00Z",
      target_info: { target_repo: "ethereum/go-ethereum" },
      notes: "ok",
    });
    const sum = summarise(m, "/abs/run/x", "/abs/run/x/manifest.json");
    expect(sum.targetRepo).toBe("ethereum/go-ethereum");
    expect(sum.status).toBe("ok");
    expect(sum.unreadable).toBe(false);
  });

  it("returns null targetRepo when target_info is null", () => {
    const m = runManifestSchema.parse({
      run_id: "x",
      started_at: "2026-05-13T12:00:00Z",
      target_info: null,
    });
    const sum = summarise(m, "/abs", "/abs/manifest.json");
    expect(sum.targetRepo).toBeNull();
  });
});

describe("readManifest", () => {
  it("reads and validates a manifest on disk", async () => {
    const path = join(dir, "manifest.json");
    await fs.writeFile(
      path,
      JSON.stringify({
        run_id: "x",
        started_at: "2026-05-13T12:00:00Z",
        notes: "ok",
      }),
    );
    const m = await readManifest(path);
    expect(m.run_id).toBe("x");
  });

  it("rejects malformed JSON", async () => {
    const path = join(dir, "manifest.json");
    await fs.writeFile(path, "not json");
    await expect(readManifest(path)).rejects.toThrow();
  });
});
