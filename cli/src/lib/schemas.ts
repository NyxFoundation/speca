/**
 * Zod schemas derived from the U2-exported JSON Schema files in `schemas/`.
 *
 * These cover the two files that `speca init` writes:
 *   - outputs/TARGET_INFO.json   (TargetInfo)
 *   - outputs/BUG_BOUNTY_SCOPE.json (BugBountyScopeInfo)
 */
import { z } from "zod";

export const TargetInfoSchema = z.object({
  target_repo: z.string().min(1, "target_repo is required"),
  target_commit: z.string().default(""),
  target_commit_short: z.string().default(""),
  target_ref_label: z.string().default(""),
  target_ref_type: z.string().default(""),
});

export type TargetInfo = z.infer<typeof TargetInfoSchema>;

export const BugBountyScopeSchema = z.object({
  program_name: z.string().default(""),
  program_url: z.string().default(""),
  in_scope_components: z.array(z.string()).default([]),
  out_of_scope_components: z.array(z.string()).default([]),
  scope_notes: z.array(z.string()).default([]),
  inherited_from: z.string().default(""),
  severity_classification: z.record(z.string(), z.unknown()).default({}),
});

export type BugBountyScopeInfo = z.infer<typeof BugBountyScopeSchema>;
