/**
 * Schema validation layer.
 *
 * Wraps Ajv (with ajv-formats) and exposes typed validators for the JSON
 * artefacts the CLI writes — `TARGET_INFO.json` and `BUG_BOUNTY_SCOPE.json`.
 *
 * The schemas live under `./generated/` and are produced by
 * `npm run sync-schemas` from the repo-root `schemas/` directory (which is in
 * turn produced by `scripts/export_schemas.py`, U2 in the CLI roadmap).
 */
import Ajv, { type ErrorObject, type ValidateFunction } from "ajv";
import addFormats from "ajv-formats";

import targetInfoSchema from "./generated/TargetInfo.schema.json" with { type: "json" };
import bugBountyScopeSchema from "./generated/BugBountyScopeInfo.schema.json" with { type: "json" };

export type ValidationResult<T> =
  | { ok: true; data: T }
  | { ok: false; errors: ValidationError[] };

export interface ValidationError {
  path: string;
  message: string;
}

function buildValidator<T>(schema: object): ValidateFunction<T> {
  // Strip our `_generated` provenance bookkeeping so Ajv does not complain
  // about the unknown root key in strict mode.
  const cleaned: Record<string, unknown> = { ...(schema as Record<string, unknown>) };
  delete cleaned._generated;

  const ajv = new Ajv({
    allErrors: true,
    strict: false,
    useDefaults: true,
  });
  addFormats(ajv);
  return ajv.compile<T>(cleaned);
}

const targetInfoValidate = buildValidator<TargetInfoInput>(targetInfoSchema as object);
const bugBountyScopeValidate = buildValidator<BugBountyScopeInput>(bugBountyScopeSchema as object);

function toErrors(errors: ErrorObject[] | null | undefined): ValidationError[] {
  if (!errors) return [];
  return errors.map((e) => ({
    path: e.instancePath || "/",
    message: `${e.message ?? "invalid"}${e.params ? ` (${JSON.stringify(e.params)})` : ""}`,
  }));
}

export interface TargetInfoInput {
  target_repo: string;
  target_ref_type?: string;
  target_ref_label?: string;
  target_commit?: string;
  target_commit_short?: string;
  // Allow extra fields the wizard adds (project_name, target_language, etc.)
  // for downstream consumers; the Pydantic model ignores them.
  [key: string]: unknown;
}

export interface BugBountyScopeInput {
  program_name?: string;
  program_url?: string;
  inherited_from?: string;
  in_scope_components?: string[];
  out_of_scope_components?: string[];
  scope_notes?: string[];
  severity_classification?: Record<string, unknown>;
  [key: string]: unknown;
}

export function validateTargetInfo(data: unknown): ValidationResult<TargetInfoInput> {
  const ok = targetInfoValidate(data);
  if (ok) {
    return { ok: true, data: data as TargetInfoInput };
  }
  return { ok: false, errors: toErrors(targetInfoValidate.errors) };
}

export function validateBugBountyScope(data: unknown): ValidationResult<BugBountyScopeInput> {
  const ok = bugBountyScopeValidate(data);
  if (ok) {
    return { ok: true, data: data as BugBountyScopeInput };
  }
  return { ok: false, errors: toErrors(bugBountyScopeValidate.errors) };
}

export function formatErrors(errors: ValidationError[]): string {
  return errors.map((e) => `  ${e.path}: ${e.message}`).join("\n");
}
