/**
 * `speca init` command — interactive project setup wizard.
 *
 * Note: this command intentionally does NOT use Ink. @clack/prompts owns
 * stdout/stderr while it runs and conflicts with Ink's reconciler. The other
 * commands (version, doctor) keep their Ink rendering; we just opt out here.
 */
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import * as p from "@clack/prompts";

import { buildArtefacts } from "../lib/init/build.js";
import { existingArtefacts, writeArtefacts } from "../lib/init/write.js";
import {
  TARGET_LANGUAGES,
  TARGET_LAYERS,
  type InitAnswers,
  type InitOverrides,
} from "../lib/init/types.js";
import {
  WizardCancelled,
  WizardMissingInput,
  buildAnswersNonInteractive,
  runInteractiveWizard,
} from "../lib/init/wizard.js";
import {
  formatErrors,
  validateBugBountyScope,
  validateTargetInfo,
} from "../lib/schemas/index.js";

export interface InitCommandFlags {
  projectName?: string;
  targetRepo?: string;
  targetCommit?: string;
  targetLanguage?: string;
  targetLayer?: string;
  rubric?: string;
  outputDir?: string;
  force?: boolean;
  yes?: boolean;
  nonInteractive?: boolean;
}

const HELP_TEXT = `\
speca init — create a new audit project

Usage
  $ speca init [flags]

Flags (all optional; missing values are prompted for)
  --project-name <name>      Project name (default: cwd basename)
  --target-repo <url>        Target repository URL, e.g. https://github.com/owner/repo
  --target-commit <ref>      Target commit / branch / tag (default: HEAD)
  --target-language <lang>   One of: ${TARGET_LANGUAGES.join(", ")}
  --target-layer <layer>     One of: ${TARGET_LAYERS.join(", ")}
  --rubric <mode>            'default' (ethereum.org rubric) or 'custom'
  --output-dir <dir>         Where to write the JSON files (default: \$SPECA_OUTPUT_DIR or ./outputs/)
  --force                    Overwrite existing TARGET_INFO.json / BUG_BOUNTY_SCOPE.json without asking
  --yes                      Same as --force; non-interactive friendly
  --non-interactive          Refuse to prompt; require all values via flags

Examples
  $ speca init
  $ speca init --target-repo https://github.com/sigp/lighthouse \\
               --target-language Rust --target-layer consensus \\
               --rubric default --output-dir ./outputs --non-interactive
`;

export type InitExitCode = 0 | 1 | 2;

function flagsToOverrides(flags: InitCommandFlags): InitOverrides {
  const overrides: InitOverrides = {
    projectName: flags.projectName,
    targetRepo: flags.targetRepo,
    targetCommit: flags.targetCommit,
    targetLanguage: flags.targetLanguage as InitOverrides["targetLanguage"],
    targetLayer: flags.targetLayer as InitOverrides["targetLayer"],
    rubricMode: flags.rubric as InitOverrides["rubricMode"],
    outputDir: flags.outputDir,
    force: flags.force || flags.yes,
    nonInteractive: flags.nonInteractive,
  };
  return overrides;
}

function isNonInteractive(flags: InitCommandFlags): boolean {
  if (flags.nonInteractive) return true;
  // If stdin is not a TTY (e.g. piped, CI), refuse to prompt.
  return process.stdin.isTTY !== true;
}

export interface RunInitOptions {
  flags: InitCommandFlags;
  // Surface tested separately; default uses real I/O.
  log?: (msg: string) => void;
  errorLog?: (msg: string) => void;
}

export async function runInitCommand({
  flags,
  log = (m) => console.log(m),
  errorLog = (m) => console.error(m),
}: RunInitOptions): Promise<InitExitCode> {
  if (flags.yes) flags.force = true;

  const overrides = flagsToOverrides(flags);
  const nonInteractive = isNonInteractive(flags);

  let answers: InitAnswers;
  try {
    if (nonInteractive) {
      answers = buildAnswersNonInteractive(overrides);
    } else {
      answers = await runInteractiveWizard(overrides);
    }
  } catch (err) {
    if (err instanceof WizardCancelled) {
      p.cancel("speca init cancelled. No files were written.");
      return 1;
    }
    if (err instanceof WizardMissingInput) {
      errorLog(`speca init: ${err.message}`);
      errorLog("Hint: pass the missing flag, or drop --non-interactive to be prompted.");
      return 2;
    }
    errorLog(`speca init: unexpected error: ${(err as Error).message}`);
    return 2;
  }

  const artefacts = buildArtefacts(answers);

  // Validate against the U2 JSON Schemas before touching disk.
  const targetInfoCheck = validateTargetInfo(artefacts.targetInfo);
  if (!targetInfoCheck.ok) {
    errorLog("TARGET_INFO.json failed schema validation:");
    errorLog(formatErrors(targetInfoCheck.errors));
    return 2;
  }
  const scopeCheck = validateBugBountyScope(artefacts.bugBountyScope);
  if (!scopeCheck.ok) {
    errorLog("BUG_BOUNTY_SCOPE.json failed schema validation:");
    errorLog(formatErrors(scopeCheck.errors));
    return 2;
  }

  // Confirm overwrite if files already exist (interactive only; --force skips).
  const existing = existingArtefacts(answers.outputDir);
  const wouldOverwrite = existing.targetInfo || existing.bugBountyScope;
  if (wouldOverwrite && !overrides.force) {
    if (nonInteractive) {
      errorLog(
        `speca init: ${existing.targetInfo ? "TARGET_INFO.json " : ""}` +
          `${existing.bugBountyScope ? "BUG_BOUNTY_SCOPE.json " : ""}` +
          `already exist in ${resolve(answers.outputDir)}. Pass --force or --yes to overwrite.`,
      );
      return 2;
    }
    const proceed = await p.confirm({
      message: `Overwrite existing files in ${resolve(answers.outputDir)}?`,
      initialValue: false,
    });
    if (p.isCancel(proceed) || proceed !== true) {
      p.cancel("speca init cancelled. No files were written.");
      return 1;
    }
  }

  const result = writeArtefacts({ outputDir: answers.outputDir, artefacts });

  log(`Wrote ${result.targetInfoPath}`);
  log(`Wrote ${result.bugBountyScopePath}`);
  if (answers.rubricMode === "custom") {
    log("");
    log("[next step] Edit BUG_BOUNTY_SCOPE.json to reflect your program's actual scope.");
  }
  if (existsSync(resolve(answers.outputDir))) {
    log("");
    log("Project initialised. Next: `speca doctor` then `speca run --phase 01a`.");
  }
  return 0;
}

export function printInitHelp(): void {
  process.stdout.write(HELP_TEXT);
}
