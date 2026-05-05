/**
 * `speca init` — interactive project wizard that writes valid
 * `outputs/TARGET_INFO.json` and `outputs/BUG_BOUNTY_SCOPE.json`.
 *
 * Uses @clack/prompts for a clean wizard UX. Validates output against
 * the Zod schemas (mirror of the U2 JSON Schemas).
 *
 * Spec ref: Issue #3 M2, SPECA_CLI_SPEC §4.5.
 */

import * as p from "@clack/prompts";
import { execFile } from "node:child_process";
import { promises as fs } from "node:fs";
import { resolve } from "node:path";
import { promisify } from "node:util";
import {
  BugBountyScopeSchema,
  TargetInfoSchema,
  type BugBountyScopeInfo,
  type TargetInfo,
} from "../lib/schemas.js";

const execFileAsync = promisify(execFile);

export interface InitOptions {
  /** Project root directory. Defaults to cwd. */
  cwd?: string;
  /** Override outputs dir (for testing). */
  outputsDir?: string;
}

function cancelled(): never {
  p.cancel("Setup cancelled.");
  process.exit(1);
}

/**
 * Resolve the short commit hash and ref info from a Git repository.
 */
async function resolveGitInfo(
  repoDir: string,
): Promise<{ commit: string; commitShort: string; refLabel: string; refType: string }> {
  const defaults = { commit: "", commitShort: "", refLabel: "", refType: "" };
  try {
    const { stdout: commitFull } = await execFileAsync("git", ["-C", repoDir, "rev-parse", "HEAD"], {
      timeout: 10000,
    });
    const commit = commitFull.trim();
    const commitShort = commit.slice(0, 7);

    // Try to resolve branch name
    let refLabel = "";
    let refType = "";
    try {
      const { stdout: branch } = await execFileAsync(
        "git",
        ["-C", repoDir, "symbolic-ref", "--short", "HEAD"],
        { timeout: 5000 },
      );
      refLabel = branch.trim();
      refType = "branch";
    } catch {
      // Detached HEAD — try tag
      try {
        const { stdout: tag } = await execFileAsync(
          "git",
          ["-C", repoDir, "describe", "--tags", "--exact-match", "HEAD"],
          { timeout: 5000 },
        );
        refLabel = tag.trim();
        refType = "tag";
      } catch {
        refLabel = commitShort;
        refType = "commit";
      }
    }
    return { commit, commitShort, refLabel, refType };
  } catch {
    return defaults;
  }
}

/**
 * Parse a comma-or-newline separated list of items from a string.
 */
function parseList(input: string): string[] {
  return input
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

export async function initCommand(opts: InitOptions = {}): Promise<number> {
  const cwd = opts.cwd ?? process.cwd();
  const outputsDir = opts.outputsDir ?? resolve(cwd, "outputs");

  p.intro("speca init — project setup wizard");

  // ── Step 1: Target repository ──────────────────────────────────────────

  const targetRepo = await p.text({
    message: "Target repository (GitHub URL or owner/repo)",
    placeholder: "https://github.com/org/repo  or  org/repo",
    validate(value) {
      if (!value || value.trim().length === 0) return "Repository is required";
      return undefined;
    },
  });
  if (p.isCancel(targetRepo)) cancelled();

  // Normalise to owner/repo format
  let repoSlug = (targetRepo as string).trim();
  const ghMatch = repoSlug.match(/github\.com\/([^/]+\/[^/]+?)(?:\.git)?(?:\/|$)/);
  if (ghMatch) repoSlug = ghMatch[1]!;

  // Try to resolve Git info if we have a local clone
  const localPaths = [
    resolve(cwd, repoSlug.split("/").pop() ?? ""),
    resolve(cwd, "target"),
  ];

  let gitInfo = { commit: "", commitShort: "", refLabel: "", refType: "" };
  for (const lp of localPaths) {
    const info = await resolveGitInfo(lp);
    if (info.commit) {
      gitInfo = info;
      break;
    }
  }

  // Ask for commit if not auto-detected
  let targetCommit = gitInfo.commit;
  let targetCommitShort = gitInfo.commitShort;
  let targetRefLabel = gitInfo.refLabel;
  let targetRefType = gitInfo.refType;

  if (!targetCommit) {
    const refInput = await p.text({
      message: "Target branch, tag, or commit hash (leave empty for HEAD)",
      placeholder: "main",
      defaultValue: "",
    });
    if (p.isCancel(refInput)) cancelled();
    const ref = (refInput as string).trim();
    if (ref) {
      if (/^[0-9a-f]{7,40}$/.test(ref)) {
        targetCommit = ref;
        targetCommitShort = ref.slice(0, 7);
        targetRefType = "commit";
        targetRefLabel = targetCommitShort;
      } else {
        targetRefLabel = ref;
        targetRefType = ref.startsWith("v") ? "tag" : "branch";
      }
    }
  } else {
    p.log.info(`Auto-detected commit: ${gitInfo.commitShort} (${gitInfo.refLabel})`);
  }

  // ── Step 2: Bug bounty scope ───────────────────────────────────────────

  const hasBounty = await p.confirm({
    message: "Does this target have a bug bounty program?",
    initialValue: false,
  });
  if (p.isCancel(hasBounty)) cancelled();

  let scope: BugBountyScopeInfo = BugBountyScopeSchema.parse({});

  if (hasBounty) {
    const programName = await p.text({
      message: "Bug bounty program name",
      placeholder: "e.g. Ethereum Foundation",
      defaultValue: "",
    });
    if (p.isCancel(programName)) cancelled();

    const programUrl = await p.text({
      message: "Bug bounty program URL",
      placeholder: "https://immunefi.com/...",
      defaultValue: "",
    });
    if (p.isCancel(programUrl)) cancelled();

    const inScopeRaw = await p.text({
      message: "In-scope components (comma-separated)",
      placeholder: "consensus, networking, EVM",
      defaultValue: "",
    });
    if (p.isCancel(inScopeRaw)) cancelled();

    const outScopeRaw = await p.text({
      message: "Out-of-scope components (comma-separated, optional)",
      placeholder: "docs, tests, CI",
      defaultValue: "",
    });
    if (p.isCancel(outScopeRaw)) cancelled();

    const scopeNotesRaw = await p.text({
      message: "Scope notes (comma-separated, optional)",
      placeholder: "Only Solidity contracts in src/",
      defaultValue: "",
    });
    if (p.isCancel(scopeNotesRaw)) cancelled();

    scope = BugBountyScopeSchema.parse({
      program_name: (programName as string).trim(),
      program_url: (programUrl as string).trim(),
      in_scope_components: parseList(inScopeRaw as string),
      out_of_scope_components: parseList(outScopeRaw as string),
      scope_notes: parseList(scopeNotesRaw as string),
    });
  }

  // ── Step 3: Validate & write ───────────────────────────────────────────

  const targetInfo: TargetInfo = TargetInfoSchema.parse({
    target_repo: repoSlug,
    target_commit: targetCommit,
    target_commit_short: targetCommitShort,
    target_ref_label: targetRefLabel,
    target_ref_type: targetRefType,
  });

  // Confirm before writing
  p.log.step("Files to create:");
  p.log.message(`  outputs/TARGET_INFO.json`);
  p.log.message(`  outputs/BUG_BOUNTY_SCOPE.json`);

  const confirm = await p.confirm({
    message: "Write these files?",
    initialValue: true,
  });
  if (p.isCancel(confirm) || !confirm) cancelled();

  // Write files
  const s = p.spinner();
  s.start("Writing project files...");

  await fs.mkdir(outputsDir, { recursive: true });

  const targetInfoPath = resolve(outputsDir, "TARGET_INFO.json");
  const scopePath = resolve(outputsDir, "BUG_BOUNTY_SCOPE.json");

  await fs.writeFile(targetInfoPath, JSON.stringify(targetInfo, null, 2) + "\n", "utf8");
  await fs.writeFile(scopePath, JSON.stringify(scope, null, 2) + "\n", "utf8");

  s.stop("Project files written.");

  p.outro("Setup complete! Run `speca doctor` to verify your environment.");
  return 0;
}
