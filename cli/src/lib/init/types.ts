/**
 * Types shared between the `speca init` wizard and its tests.
 */

export const TARGET_LANGUAGES = [
  "Solidity",
  "Rust",
  "Go",
  "Python",
  "TypeScript",
  "Other",
] as const;
export type TargetLanguage = (typeof TARGET_LANGUAGES)[number];

export const TARGET_LAYERS = [
  "execution",
  "consensus",
  "l2-node",
  "smart-contract",
  "other",
] as const;
export type TargetLayer = (typeof TARGET_LAYERS)[number];

export const RUBRIC_MODES = ["default", "custom"] as const;
export type RubricMode = (typeof RUBRIC_MODES)[number];

export interface InitAnswers {
  projectName: string;
  targetRepo: string;
  targetCommit: string;
  targetLanguage: TargetLanguage;
  targetLayer: TargetLayer;
  rubricMode: RubricMode;
  outputDir: string;
}

export interface InitOverrides {
  projectName?: string;
  targetRepo?: string;
  targetCommit?: string;
  targetLanguage?: TargetLanguage;
  targetLayer?: TargetLayer;
  rubricMode?: RubricMode;
  outputDir?: string;
  // When true, never prompt — fail loudly if any required field is missing.
  nonInteractive?: boolean;
  // When true, overwrite without confirmation.
  force?: boolean;
}

export interface BuiltArtefacts {
  targetInfo: Record<string, unknown>;
  bugBountyScope: Record<string, unknown>;
}

export const TARGET_REPO_PATTERN = /^https:\/\/github\.com\/[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+(?:\.git)?$/;

export function validateTargetRepo(value: string | undefined): string | undefined {
  if (!value || value.trim() === "") return "target repo URL is required";
  if (!TARGET_REPO_PATTERN.test(value.trim())) {
    return "must look like https://github.com/owner/repo";
  }
  return undefined;
}

export function validateProjectName(value: string | undefined): string | undefined {
  if (!value || value.trim() === "") return "project name is required";
  if (!/^[A-Za-z0-9._-]+$/.test(value.trim())) {
    return "use only letters, digits, dot, underscore or dash";
  }
  return undefined;
}

export function isTargetLanguage(value: unknown): value is TargetLanguage {
  return typeof value === "string" && (TARGET_LANGUAGES as readonly string[]).includes(value);
}

export function isTargetLayer(value: unknown): value is TargetLayer {
  return typeof value === "string" && (TARGET_LAYERS as readonly string[]).includes(value);
}

export function isRubricMode(value: unknown): value is RubricMode {
  return typeof value === "string" && (RUBRIC_MODES as readonly string[]).includes(value);
}
