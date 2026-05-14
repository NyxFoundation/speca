/**
 * `speca corpus` subcommand dispatcher.
 *
 * Mirrors the pattern used by `speca auth` (see cli.tsx::runAuth). Keeps
 * the corpus surface in one place so `cli.tsx` doesn't grow another giant
 * switch arm.
 */
import { render } from "ink";

import { CorpusListCommand } from "./list.js";
import { CorpusShowCommand } from "./show.js";
import { runCorpusGcCommand, CORPUS_GC_HELP } from "./gc.js";
import type { CorpusGcFlags } from "./gc.js";
import { runCorpusExportCommand, CORPUS_EXPORT_HELP } from "./export.js";
import type { CorpusExportFlags } from "./export.js";

export const CORPUS_HELP = `\
speca corpus — browse and share per-run trace archives (.speca/runs/)

Usage
  $ speca corpus <subcommand>

Subcommands
  list                       Tabular view of all runs in the archive
  show <run-id>              Manifest + per-phase summary
  export <run-id> [flags]    Redacted slice ready to share (default: 01a,01b,01e)
  gc --older-than <dur>      Soft-delete old runs (default: --dry-run)

See \`speca corpus <subcmd> --help\` for subcommand-specific flags.
`;

interface CorpusInvocation {
  subcommand: string | undefined;
  positional: string | undefined;
  flags: CorpusGcFlags & CorpusExportFlags;
  helpRequested: boolean;
}

export async function runCorpus(inv: CorpusInvocation): Promise<number> {
  const { subcommand, positional, flags, helpRequested } = inv;

  if (subcommand === undefined || subcommand === "help") {
    process.stdout.write(CORPUS_HELP);
    return 0;
  }

  switch (subcommand) {
    case "list": {
      if (helpRequested) {
        process.stdout.write(
          `speca corpus list — table view of every run-id under the archive root.\n\n` +
            `Flags\n` +
            `  --archive-root <path>    Override the default <cwd>/.speca/runs lookup\n`,
        );
        return 0;
      }
      const app = render(<CorpusListCommand archiveRootOverride={flags.archiveRoot} />);
      try {
        await app.waitUntilExit();
        return 0;
      } catch {
        return 1;
      }
    }
    case "show": {
      if (helpRequested) {
        process.stdout.write(
          `speca corpus show <run-id> — manifest + per-phase summary.\n\n` +
            `Flags\n` +
            `  --archive-root <path>    Override the default <cwd>/.speca/runs lookup\n`,
        );
        return 0;
      }
      if (!positional) {
        process.stderr.write("error: <run-id> argument is required for `corpus show`\n");
        return 2;
      }
      const app = render(
        <CorpusShowCommand runId={positional} archiveRootOverride={flags.archiveRoot} />,
      );
      try {
        await app.waitUntilExit();
        return 0;
      } catch {
        return 1;
      }
    }
    case "export": {
      if (helpRequested) {
        process.stdout.write(CORPUS_EXPORT_HELP);
        return 0;
      }
      return runCorpusExportCommand(positional, flags);
    }
    case "gc": {
      if (helpRequested) {
        process.stdout.write(CORPUS_GC_HELP);
        return 0;
      }
      return runCorpusGcCommand(flags);
    }
    default:
      process.stderr.write(`Unknown corpus subcommand: ${subcommand}\n`);
      process.stderr.write(CORPUS_HELP);
      return 2;
  }
}
