/**
 * Filesystem side-effects for the wizard. Pulled into its own module so the
 * pure builders can be tested without touching disk.
 */
import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import type { BuiltArtefacts } from "./types.js";

export interface WriteResult {
  targetInfoPath: string;
  bugBountyScopePath: string;
  overwritten: { targetInfo: boolean; bugBountyScope: boolean };
}

export interface WriteOptions {
  outputDir: string;
  artefacts: BuiltArtefacts;
}

function writeJson(path: string, value: unknown): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

export function writeArtefacts(opts: WriteOptions): WriteResult {
  const outDir = resolve(opts.outputDir);
  const targetInfoPath = join(outDir, "TARGET_INFO.json");
  const bugBountyScopePath = join(outDir, "BUG_BOUNTY_SCOPE.json");

  const overwritten = {
    targetInfo: existsSync(targetInfoPath),
    bugBountyScope: existsSync(bugBountyScopePath),
  };

  writeJson(targetInfoPath, opts.artefacts.targetInfo);
  writeJson(bugBountyScopePath, opts.artefacts.bugBountyScope);

  return { targetInfoPath, bugBountyScopePath, overwritten };
}

export function existingArtefacts(outputDir: string): { targetInfo: boolean; bugBountyScope: boolean } {
  const outDir = resolve(outputDir);
  return {
    targetInfo: existsSync(join(outDir, "TARGET_INFO.json")),
    bugBountyScope: existsSync(join(outDir, "BUG_BOUNTY_SCOPE.json")),
  };
}
