import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const __dirname = dirname(fileURLToPath(import.meta.url));
const cliRoot = resolve(__dirname, "..");
const scriptPath = resolve(cliRoot, "scripts", "sync-schemas.mjs");
const generatedDir = resolve(cliRoot, "src", "lib", "schemas", "generated");

describe("sync-schemas.mjs", () => {
  it("runs and writes the expected schema files", () => {
    execFileSync(process.execPath, [scriptPath], { cwd: cliRoot, stdio: "pipe" });

    expect(existsSync(resolve(generatedDir, "TargetInfo.schema.json"))).toBe(true);
    expect(existsSync(resolve(generatedDir, "BugBountyScopeInfo.schema.json"))).toBe(true);
    expect(existsSync(resolve(generatedDir, "manifest.json"))).toBe(true);
    expect(existsSync(resolve(generatedDir, "README.md"))).toBe(true);

    // Sanity: a mtime is recorded (no specific value asserted to avoid
    // FAT/NTFS clock-resolution flakiness).
    const targetPath = resolve(generatedDir, "TargetInfo.schema.json");
    expect(statSync(targetPath).mtimeMs).toBeGreaterThan(0);
  });

  it("embeds an _generated provenance block in each JSON schema", () => {
    execFileSync(process.execPath, [scriptPath], { cwd: cliRoot, stdio: "pipe" });
    const targetInfo = JSON.parse(
      readFileSync(resolve(generatedDir, "TargetInfo.schema.json"), "utf8"),
    );
    expect(targetInfo._generated).toBeDefined();
    expect(targetInfo._generated.note).toMatch(/AUTO-GENERATED/);
    expect(targetInfo._generated.generator).toMatch(/sync-schemas\.mjs/);
    expect(targetInfo.required).toContain("target_repo");
  });

  it("manifest lists the synced schema names", () => {
    execFileSync(process.execPath, [scriptPath], { cwd: cliRoot, stdio: "pipe" });
    const manifest = JSON.parse(
      readFileSync(resolve(generatedDir, "manifest.json"), "utf8"),
    );
    expect(manifest.schemas).toContain("TargetInfo.schema.json");
    expect(manifest.schemas).toContain("BugBountyScopeInfo.schema.json");
  });
});
