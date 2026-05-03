/**
 * Pure builders that turn wizard answers into the JSON artefacts
 * (`TARGET_INFO.json`, `BUG_BOUNTY_SCOPE.json`).
 *
 * Keeping these pure makes them trivially testable and lets us reuse them
 * from a future non-Ink front-end.
 */
import defaultRubric from "../../templates/bug_bounty_rubric_default.json" with { type: "json" };
import type { BuiltArtefacts, InitAnswers } from "./types.js";

interface DefaultRubric {
  program_name: string;
  program_url: string;
  inherited_from: string;
  in_scope_components: string[];
  out_of_scope_components: string[];
  scope_notes: string[];
  severity_classification: Record<string, unknown>;
  _provenance?: Record<string, unknown>;
}

function cloneDefaultRubric(): DefaultRubric {
  // structuredClone is available on Node 17+, but we still depend on it being
  // a Plain JSON value. Fall back to JSON parse/stringify if not.
  if (typeof structuredClone === "function") {
    return structuredClone(defaultRubric) as DefaultRubric;
  }
  return JSON.parse(JSON.stringify(defaultRubric)) as DefaultRubric;
}

export function buildTargetInfo(answers: InitAnswers): Record<string, unknown> {
  return {
    target_repo: answers.targetRepo.trim(),
    target_ref_type: answers.targetCommit.trim().toUpperCase() === "HEAD" ? "head" : "commit",
    target_ref_label: answers.targetCommit.trim(),
    target_commit: answers.targetCommit.trim() === "HEAD" ? "" : answers.targetCommit.trim(),
    target_commit_short: "",
    // Extra fields the orchestrator ignores but the TUI surfaces.
    project_name: answers.projectName,
    target_language: answers.targetLanguage,
    target_layer: answers.targetLayer,
  };
}

export function buildBugBountyScope(answers: InitAnswers): Record<string, unknown> {
  const rubric = cloneDefaultRubric();
  if (answers.rubricMode === "default") {
    return {
      program_name: rubric.program_name,
      program_url: rubric.program_url,
      inherited_from: rubric.inherited_from,
      in_scope_components: rubric.in_scope_components,
      out_of_scope_components: rubric.out_of_scope_components,
      scope_notes: rubric.scope_notes,
      severity_classification: rubric.severity_classification,
      _provenance: rubric._provenance,
    };
  }
  // "custom" mode: still seed with the default and instruct the user to edit.
  // Phase 01e fails loudly if severity_classification is malformed, so we
  // always emit a complete-but-editable starting point.
  return {
    program_name: `${answers.projectName} (edit me)`,
    program_url: "",
    inherited_from: rubric.inherited_from,
    in_scope_components: [],
    out_of_scope_components: [],
    scope_notes: [
      "TODO: replace this placeholder with the actual program scope.",
      "The severity_classification block below is the ethereum.org default — adjust as needed.",
    ],
    severity_classification: rubric.severity_classification,
    _provenance: {
      ...rubric._provenance,
      custom: true,
      note: "User chose 'custom' rubric mode; ethereum.org default was seeded as a starting point. Edit before running Phase 01e.",
    },
  };
}

export function buildArtefacts(answers: InitAnswers): BuiltArtefacts {
  return {
    targetInfo: buildTargetInfo(answers),
    bugBountyScope: buildBugBountyScope(answers),
  };
}
