/**
 * Interactive `speca init` wizard powered by @clack/prompts.
 *
 * The wizard collects answers, applies CLI flag overrides, and returns a
 * fully-resolved `InitAnswers`. The actual file writing happens in
 * `write.ts` so this module is easy to swap or test.
 */
import { basename, resolve } from "node:path";
import * as p from "@clack/prompts";

import {
  type InitAnswers,
  type InitOverrides,
  TARGET_LANGUAGES,
  TARGET_LAYERS,
  type TargetLanguage,
  type TargetLayer,
  isRubricMode,
  isTargetLanguage,
  isTargetLayer,
  validateProjectName,
  validateTargetRepo,
} from "./types.js";

export class WizardCancelled extends Error {
  constructor() {
    super("wizard cancelled by user");
    this.name = "WizardCancelled";
  }
}

export class WizardMissingInput extends Error {
  constructor(field: string) {
    super(`required field missing in non-interactive mode: ${field}`);
    this.name = "WizardMissingInput";
  }
}

function defaultOutputDir(): string {
  return process.env.SPECA_OUTPUT_DIR ?? "./outputs/";
}

function defaultProjectName(): string {
  return basename(resolve(process.cwd())) || "speca-project";
}

function ensureOrThrow<T>(value: T | symbol): T {
  if (p.isCancel(value)) {
    throw new WizardCancelled();
  }
  return value as T;
}

export interface RunWizardDeps {
  // Injection points so tests can stub clack without spinning a real TTY.
  promptText?: typeof p.text;
  promptSelect?: typeof p.select;
  promptConfirm?: typeof p.confirm;
  intro?: typeof p.intro;
  outro?: typeof p.outro;
  note?: typeof p.note;
  cancel?: typeof p.cancel;
}

/**
 * Resolve answers without any prompting. Used in non-interactive mode and as
 * the override layer in interactive mode.
 */
export function resolveFromOverrides(overrides: InitOverrides): Partial<InitAnswers> {
  const partial: Partial<InitAnswers> = {};
  if (overrides.projectName) partial.projectName = overrides.projectName;
  if (overrides.targetRepo) partial.targetRepo = overrides.targetRepo;
  if (overrides.targetCommit) partial.targetCommit = overrides.targetCommit;
  if (overrides.targetLanguage) partial.targetLanguage = overrides.targetLanguage;
  if (overrides.targetLayer) partial.targetLayer = overrides.targetLayer;
  if (overrides.rubricMode) partial.rubricMode = overrides.rubricMode;
  if (overrides.outputDir) partial.outputDir = overrides.outputDir;
  return partial;
}

export function buildAnswersNonInteractive(overrides: InitOverrides): InitAnswers {
  const partial = resolveFromOverrides(overrides);
  const projectName = partial.projectName ?? defaultProjectName();
  const targetCommit = partial.targetCommit ?? "HEAD";
  const rubricMode = partial.rubricMode ?? "default";
  const outputDir = partial.outputDir ?? defaultOutputDir();

  if (!partial.targetRepo) throw new WizardMissingInput("targetRepo (--target-repo)");
  const repoErr = validateTargetRepo(partial.targetRepo);
  if (repoErr) throw new WizardMissingInput(`targetRepo: ${repoErr}`);

  if (!partial.targetLanguage) throw new WizardMissingInput("targetLanguage (--target-language)");
  if (!isTargetLanguage(partial.targetLanguage)) {
    throw new WizardMissingInput(
      `targetLanguage must be one of: ${TARGET_LANGUAGES.join(", ")}`,
    );
  }

  if (!partial.targetLayer) throw new WizardMissingInput("targetLayer (--target-layer)");
  if (!isTargetLayer(partial.targetLayer)) {
    throw new WizardMissingInput(
      `targetLayer must be one of: ${TARGET_LAYERS.join(", ")}`,
    );
  }

  if (!isRubricMode(rubricMode)) {
    throw new WizardMissingInput(`rubricMode must be 'default' or 'custom'`);
  }

  const projectErr = validateProjectName(projectName);
  if (projectErr) throw new WizardMissingInput(`projectName: ${projectErr}`);

  return {
    projectName,
    targetRepo: partial.targetRepo,
    targetCommit,
    targetLanguage: partial.targetLanguage,
    targetLayer: partial.targetLayer,
    rubricMode,
    outputDir,
  };
}

export async function runInteractiveWizard(
  overrides: InitOverrides,
  deps: RunWizardDeps = {},
): Promise<InitAnswers> {
  const promptText = deps.promptText ?? p.text;
  const promptSelect = deps.promptSelect ?? p.select;
  const intro = deps.intro ?? p.intro;
  const outro = deps.outro ?? p.outro;
  const note = deps.note ?? p.note;

  const partial = resolveFromOverrides(overrides);

  intro("speca init — new audit project");

  const projectName =
    partial.projectName ??
    ensureOrThrow(
      await promptText({
        message: "Project name",
        placeholder: defaultProjectName(),
        defaultValue: defaultProjectName(),
        validate: (v) => validateProjectName(v),
      }),
    );

  const targetRepo =
    partial.targetRepo ??
    ensureOrThrow(
      await promptText({
        message: "Target repository URL (https://github.com/owner/repo)",
        placeholder: "https://github.com/owner/repo",
        validate: (v) => validateTargetRepo(v),
      }),
    );

  const targetCommit =
    partial.targetCommit ??
    ensureOrThrow(
      await promptText({
        message: "Target commit (branch name, tag, or SHA — leave HEAD to resolve later)",
        placeholder: "HEAD",
        defaultValue: "HEAD",
      }),
    );

  const targetLanguage =
    partial.targetLanguage ??
    (ensureOrThrow(
      await promptSelect<TargetLanguage>({
        message: "Target language",
        options: TARGET_LANGUAGES.map((v) => ({ value: v, label: v })),
      }),
    ) as TargetLanguage);

  const targetLayer =
    partial.targetLayer ??
    (ensureOrThrow(
      await promptSelect<TargetLayer>({
        message: "Target layer",
        options: TARGET_LAYERS.map((v) => ({ value: v, label: v })),
      }),
    ) as TargetLayer);

  const rubricMode =
    partial.rubricMode ??
    (ensureOrThrow(
      await promptSelect<"default" | "custom">({
        message: "Bug bounty severity rubric",
        options: [
          { value: "default", label: "Use ethereum.org default", hint: "ready to go" },
          { value: "custom", label: "Custom (write template, edit later)", hint: "manual edit" },
        ],
      }),
    ) as "default" | "custom");

  if (rubricMode === "custom") {
    note(
      "We will write the ethereum.org default as a starting point.\nEdit BUG_BOUNTY_SCOPE.json before running Phase 01e.",
      "custom rubric",
    );
  }

  const outputDir =
    partial.outputDir ??
    ensureOrThrow(
      await promptText({
        message: "Output directory",
        placeholder: defaultOutputDir(),
        defaultValue: defaultOutputDir(),
      }),
    );

  const answers: InitAnswers = {
    projectName: projectName.trim(),
    targetRepo: targetRepo.trim(),
    targetCommit: targetCommit.trim() || "HEAD",
    targetLanguage,
    targetLayer,
    rubricMode,
    outputDir: outputDir.trim() || defaultOutputDir(),
  };

  outro("Wizard complete. Writing project files…");
  return answers;
}
