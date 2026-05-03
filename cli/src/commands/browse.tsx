/**
 * `speca browse` — open the M4 finding browser.
 *
 * Reads Phase 03 / Phase 04 PARTIAL JSON files (default glob:
 * `outputs/04_PARTIAL_*.json`), merges + dedupes by `property_id`, and hands
 * the result to the Ink `<FindingBrowser />` component.
 *
 * The `--no-tui` flag is reserved for the M6 "plain-text output" milestone.
 * For M4 we fall back to a JSON dump on stdout when set, so CI scripts can
 * already start consuming the loader output without waiting for M6.
 */
import { render } from "ink";
import { createElement } from "react";

import { FindingBrowser } from "../components/FindingBrowser.js";
import { loadFindings } from "../lib/findings/loader.js";
import { applyFilter } from "../lib/findings/filter.js";

export interface BrowseFlags {
  filter?: string;
  severity?: string;
  verdict?: string;
  noTui?: boolean;
  json?: boolean;
}

export const BROWSE_HELP = `\
speca browse — explore Phase 04 audit findings in a TUI

Usage
  $ speca browse [glob]          (default: outputs/04_PARTIAL_*.json)

Flags
  --filter <dsl>                 Pre-apply a filter, e.g. --filter "severity:High AND verdict:CONFIRMED_*"
  --severity <level>             Shorthand for --filter "severity:<level>"
  --verdict <verdict>            Shorthand for --filter "verdict:<verdict>"
  --no-tui                       Plain-text JSON pass-through (M6: dump matched findings to stdout)
  --json                         Same as --no-tui

Filter DSL
  severity:Critical              exact severity match (case-insensitive)
  severity:Critical,High         comma-separated OR
  verdict:CONFIRMED_*            wildcard suffix
  prop:PROP-6a4*                 wildcard match against property_id
  repo:lighthouse                substring match against source file path
  text:reentrancy                substring search in summary/proof/attack/notes
  severity:High AND verdict:CONFIRMED_*   explicit AND
  NOT verdict:DISPUTED_FP        negation
  (severity:High OR severity:Critical) AND prop:PROP-6a4*  parens

Keybindings (TUI)
  ↑/↓ k/j   move selection           Enter      toggle expanded detail
  c          load code peek           f          edit filter
  /          quick text search        s          cycle sort mode
  r          reload from disk         q          quit

Examples
  $ speca browse
  $ speca browse outputs/04_PARTIAL_*.json
  $ speca browse --severity Critical
  $ speca browse --filter "severity:High AND verdict:CONFIRMED_*"
`;

interface RunBrowseOptions {
  flags: BrowseFlags;
  positional: string[];
  cwd?: string;
}

const DEFAULT_GLOB = "outputs/04_PARTIAL_*.json";

export function buildInitialFilter(flags: BrowseFlags): string {
  const parts: string[] = [];
  if (flags.filter && flags.filter.trim().length > 0) parts.push(flags.filter.trim());
  if (flags.severity && flags.severity.trim().length > 0) parts.push(`severity:${flags.severity.trim()}`);
  if (flags.verdict && flags.verdict.trim().length > 0) parts.push(`verdict:${flags.verdict.trim()}`);
  return parts.join(" AND ");
}

export async function runBrowseCommand(options: RunBrowseOptions): Promise<number> {
  const { flags, positional } = options;
  const cwd = options.cwd ?? process.cwd();
  const globs = positional.length > 0 ? positional : [DEFAULT_GLOB];
  const initial = await loadFindings(globs, { cwd });
  const initialFilter = buildInitialFilter(flags);

  if (flags.noTui || flags.json) {
    const { matched, result } = applyFilter(initial.findings, initialFilter);
    if (!result.ok) {
      process.stderr.write(`speca browse: invalid filter: ${result.message}\n`);
      return 2;
    }
    const payload = {
      source: globs,
      filter: initialFilter,
      total: initial.findings.length,
      matched: matched.length,
      warnings: initial.warnings,
      findings: matched,
    };
    process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
    return 0;
  }

  if (initial.findings.length === 0 && initial.files.length === 0) {
    process.stderr.write(
      `speca browse: no files matched ${globs.join(" ")} under ${cwd}.\n` +
        "Hint: pass an explicit glob or run from a project directory containing outputs/.\n",
    );
    return 1;
  }

  const app = render(
    createElement(FindingBrowser, {
      initial,
      globs,
      initialFilter,
      cwd,
    }),
  );
  await app.waitUntilExit();
  return 0;
}
