/**
 * Archive-root resolver for `speca corpus` subcommands.
 *
 * Precedence (matches the Python orchestrator's run_phase.py):
 *   1. CLI override via the caller (passed in as `explicit`)
 *   2. `SPECA_ARCHIVE_ROOT` env var
 *   3. `<cwd>/.speca/runs` — the orchestrator default
 *
 * Returning a resolved absolute path lets every downstream caller use plain
 * `path.join` without worrying about whether the user invoked `speca corpus`
 * from a sub-directory of the audit repo.
 */
import { resolve } from "node:path";

export function archiveRoot(explicit?: string): string {
  if (explicit && explicit.trim()) {
    return resolve(explicit.trim());
  }
  const env = process.env.SPECA_ARCHIVE_ROOT;
  if (env && env.trim()) {
    return resolve(env.trim());
  }
  return resolve(process.cwd(), ".speca", "runs");
}
