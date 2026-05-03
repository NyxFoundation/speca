import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  clearSession,
  loadSession,
  newSessionInfo,
  saveSession,
  sessionFilePath,
  sessionPaths,
  touchSessionInfo,
  type SessionInfo,
} from "../src/lib/claude-session/store.js";

let workDir: string;

beforeEach(async () => {
  workDir = await fs.mkdtemp(join(tmpdir(), "speca-session-test-"));
});

afterEach(async () => {
  await fs.rm(workDir, { recursive: true, force: true });
});

describe("sessionPaths / sessionFilePath", () => {
  it("computes <projectRoot>/.speca/session.json", () => {
    const p = sessionPaths(workDir);
    expect(p.projectRoot).toBe(workDir);
    expect(p.dir).toBe(join(workDir, ".speca"));
    expect(p.file).toBe(join(workDir, ".speca", "session.json"));
    expect(sessionFilePath(workDir)).toBe(p.file);
  });
});

describe("loadSession / saveSession round-trip", () => {
  it("returns null when the project has no session file", async () => {
    const info = await loadSession(workDir);
    expect(info).toBeNull();
  });

  it("persists a fresh SessionInfo and re-reads it byte-for-byte", async () => {
    const fresh = newSessionInfo("9f1c-abc", 12_345, 1_700_000_000_000);
    await saveSession(fresh, workDir);
    const back = await loadSession(workDir);
    expect(back).toEqual(fresh);
  });

  it("creates the .speca directory if it doesn't exist", async () => {
    const fresh = newSessionInfo("9f1c-abc");
    await saveSession(fresh, workDir);
    const stat = await fs.stat(join(workDir, ".speca"));
    expect(stat.isDirectory()).toBe(true);
  });

  it("does not leave a tmp file behind on success", async () => {
    await saveSession(newSessionInfo("xyz"), workDir);
    const entries = await fs.readdir(join(workDir, ".speca"));
    expect(entries).toContain("session.json");
    expect(entries.filter((e) => e.endsWith(".tmp"))).toEqual([]);
  });

  it("returns null for malformed JSON instead of throwing", async () => {
    await fs.mkdir(join(workDir, ".speca"), { recursive: true });
    await fs.writeFile(join(workDir, ".speca", "session.json"), "{ not json", "utf8");
    const info = await loadSession(workDir);
    expect(info).toBeNull();
  });

  it("returns null for JSON that is not a valid SessionInfo shape", async () => {
    await fs.mkdir(join(workDir, ".speca"), { recursive: true });
    await fs.writeFile(
      join(workDir, ".speca", "session.json"),
      JSON.stringify({ not_a_session: true }),
      "utf8",
    );
    const info = await loadSession(workDir);
    expect(info).toBeNull();
  });
});

describe("touchSessionInfo", () => {
  it("bumps last_used_at while preserving identity fields", () => {
    const before: SessionInfo = newSessionInfo("sess-1", 100, 1_000);
    const after = touchSessionInfo(before, undefined, 9_999);
    expect(after.session_id).toBe("sess-1");
    expect(after.created_at).toBe(1_000);
    expect(after.last_used_at).toBe(9_999);
    expect(after.finding_context_bytes).toBe(100);
  });

  it("optionally updates finding_context_bytes", () => {
    const before: SessionInfo = newSessionInfo("sess-1", 100, 1_000);
    const after = touchSessionInfo(before, 50_000, 2_000);
    expect(after.finding_context_bytes).toBe(50_000);
    expect(after.last_used_at).toBe(2_000);
  });
});

describe("clearSession", () => {
  it("removes the session file when present", async () => {
    await saveSession(newSessionInfo("doomed"), workDir);
    expect(await loadSession(workDir)).not.toBeNull();
    expect(await clearSession(workDir)).toBe(true);
    expect(await loadSession(workDir)).toBeNull();
  });

  it("returns false when the file is already absent", async () => {
    expect(await clearSession(workDir)).toBe(false);
  });
});
