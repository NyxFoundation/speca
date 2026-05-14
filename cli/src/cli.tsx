#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { render } from "ink";
import meow from "meow";
import { createElement } from "react";
import { printAskHelp, runAskCommand } from "./commands/ask.js";
import { LOGIN_HELP, loginCommand, loginFlagsSchema } from "./commands/auth/login.js";
import { StatusCommand } from "./commands/auth/status.js";
import { BROWSE_HELP, runBrowseCommand } from "./commands/browse.js";
import { CORPUS_HELP, runCorpus } from "./commands/corpus/index.js";
import { DoctorCommand } from "./commands/doctor.js";
import { printInitHelp, runInitCommand } from "./commands/init.js";
import { printRunHelp, runRunCommand } from "./commands/run.js";
import { VersionCommand } from "./commands/version.js";
import { parseFlags } from "./lib/cli-flags/index.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

interface PackageJsonShape {
  version: string;
}

function readPackageVersion(): string {
  // dist/cli.js → ../package.json (also works under tsx where __dirname is src/)
  for (const candidate of [resolve(__dirname, "..", "package.json"), resolve(__dirname, "..", "..", "package.json")]) {
    try {
      const raw = readFileSync(candidate, "utf8");
      const pkg = JSON.parse(raw) as PackageJsonShape;
      if (pkg.version) return pkg.version;
    } catch {
      // try next candidate
    }
  }
  return "unknown";
}

const cli = meow(
  `
  Usage
    $ speca <command>

  Commands
    version            Print speca-cli version
    doctor             Check Node / uv / git / claude-code / auth status
    auth <subcommand>  Manage Anthropic credentials (login | status)
    init               Create a new audit project (TARGET_INFO + BUG_BOUNTY_SCOPE)
    run                Run pipeline phases with a live dashboard
    browse [glob]      Open the finding browser on Phase 03/04 PARTIAL JSON
    ask [finding-id]   Chat with Claude about a finding (claude-code session)
    corpus <sub>       Browse / export run archives (list | show | export | gc)
    help               Print this help

  Common flags (reserved for future milestones)
    --no-tui           Force plain-text output (M6)
    --json             Emit machine-readable events on stdout (M3)

  Auth-specific flags (only consumed under 'auth login')
    --api-key <key>    Skip OAuth and persist an Anthropic API key
    --mode <max|console>
                       OAuth entitlement source (default: max)

  Examples
    $ speca doctor
    $ speca version
    $ speca auth status
    $ speca auth login
    $ speca auth login --api-key sk-ant-api03-...
    $ speca init
`,
  {
    importMeta: import.meta,
    flags: {
      // `--no-tui` is translated by meow into `tui: false`. We model the
      // positive form here so subcommands can do `flags.tui === false` to
      // detect the no-tui flag without depending on meow internals.
      tui: { type: "boolean", default: true },
      noTui: { type: "boolean", default: false },
      json: { type: "boolean", default: false },
      // `auth login` flags
      apiKey: { type: "string" },
      mode: { type: "string" },
      // `speca init` flags (ignored by other commands)
      projectName: { type: "string" },
      targetRepo: { type: "string" },
      targetCommit: { type: "string" },
      targetLanguage: { type: "string" },
      targetLayer: { type: "string" },
      rubric: { type: "string" },
      outputDir: { type: "string" },
      force: { type: "boolean", default: false },
      yes: { type: "boolean", default: false },
      nonInteractive: { type: "boolean", default: false },
      // `speca run` flags (M3)
      phase: { type: "string", isMultiple: true },
      target: { type: "string" },
      workers: { type: "number" },
      maxConcurrent: { type: "number" },
      budget: { type: "number" },
      // `speca browse` flags (ignored by other commands)
      filter: { type: "string" },
      severity: { type: "string" },
      verdict: { type: "string" },
      // `speca ask` flags (ignored by other commands)
      from: { type: "string" },
      session: { type: "string" },
      maxContext: { type: "number" },
      // `speca corpus` flags (shared by gc / export / list / show)
      archiveRoot: { type: "string" },
      out: { type: "string" },
      includeLogs: { type: "boolean", default: false },
      phases: { type: "string" },
      olderThan: { type: "string" },
      dryRun: { type: "boolean", default: true },
      unsafeIncludeFindings: { type: "boolean", default: false },
    },
    autoHelp: false,
    autoVersion: false,
    allowUnknownFlags: true,
  },
);

const command = cli.input[0] ?? "help";
const subcommand = cli.input[1];
const version = readPackageVersion();

function isHelpFlag(): boolean {
  return process.argv.includes("--help") || process.argv.includes("-h");
}

async function runAuth(): Promise<number> {
  if (subcommand === undefined || subcommand === "help") {
    process.stdout.write(`Usage
  $ speca auth <subcommand>

Subcommands
  login    Log in to Anthropic (OAuth paste-code flow or --api-key)
  status   Show currently saved accounts

See 'speca auth login --help' for login-specific flags.
`);
    return 0;
  }
  switch (subcommand) {
    case "login": {
      if (isHelpFlag()) {
        process.stdout.write(LOGIN_HELP);
        return 0;
      }
      const parsed = parseFlags(loginFlagsSchema, cli.flags as Record<string, unknown>, "speca auth login");
      if (!parsed.ok) {
        process.stderr.write(parsed.message);
        return 2;
      }
      return loginCommand({
        apiKey: parsed.flags.apiKey,
        mode: parsed.flags.mode,
      });
    }
    case "status": {
      const app = render(createElement(StatusCommand));
      try {
        await app.waitUntilExit();
        return 0;
      } catch {
        return 1;
      }
    }
    default:
      process.stderr.write(`Unknown auth subcommand: ${subcommand}\n`);
      return 1;
  }
}

async function run(): Promise<number> {
  switch (command) {
    case "version":
    case "--version":
    case "-v": {
      const app = render(createElement(VersionCommand, { version }));
      await app.waitUntilExit();
      return 0;
    }
    case "doctor": {
      const app = render(createElement(DoctorCommand));
      try {
        await app.waitUntilExit();
        return 0;
      } catch {
        return 1;
      }
    }
    case "auth":
      return runAuth();
    case "browse": {
      if (subcommand === "help" || isHelpFlag()) {
        process.stdout.write(BROWSE_HELP);
        return 0;
      }
      // Treat any positional arg after `browse` as a glob.
      const positional = cli.input.slice(1);
      // meow normalises `--no-tui` to `tui: false` rather than `noTui: true`,
      // so we honour both spellings here. Same idea for `--no-json`.
      const noTui =
        cli.flags.noTui === true ||
        process.argv.includes("--no-tui") ||
        process.argv.includes("--no-tty");
      return runBrowseCommand({
        flags: {
          filter: cli.flags.filter,
          severity: cli.flags.severity,
          verdict: cli.flags.verdict,
          noTui,
          json: cli.flags.json,
        },
        positional,
      });
    }
    case "init": {
      const wantsHelp = subcommand === "help" || isHelpFlag();
      if (wantsHelp) {
        printInitHelp();
        return 0;
      }
      const code = await runInitCommand({
        flags: {
          projectName: cli.flags.projectName,
          targetRepo: cli.flags.targetRepo,
          targetCommit: cli.flags.targetCommit,
          targetLanguage: cli.flags.targetLanguage,
          targetLayer: cli.flags.targetLayer,
          rubric: cli.flags.rubric,
          outputDir: cli.flags.outputDir,
          force: cli.flags.force,
          yes: cli.flags.yes,
          nonInteractive: cli.flags.nonInteractive,
        },
      });
      return code;
    }
    case "run": {
      const wantsHelp = subcommand === "help" || isHelpFlag();
      if (wantsHelp) {
        printRunHelp();
        return 0;
      }
      const phaseFlag = cli.flags.phase as string | string[] | undefined;
      const code = await runRunCommand({
        flags: {
          phase: Array.isArray(phaseFlag) ? phaseFlag : phaseFlag != null ? [phaseFlag] : undefined,
          target: cli.flags.target,
          workers: cli.flags.workers,
          maxConcurrent: cli.flags.maxConcurrent,
          force: cli.flags.force,
          budget: cli.flags.budget,
          noTui: cli.flags.noTui,
          json: cli.flags.json,
          outputDir: cli.flags.outputDir,
        },
      });
      return code;
    }
    case "ask": {
      const wantsHelp = subcommand === "help" || isHelpFlag();
      if (wantsHelp) {
        printAskHelp();
        return 0;
      }
      // Positional after "ask" is the optional finding-id.
      const positional = cli.input.slice(1);
      return runAskCommand({
        positional,
        flags: {
          from: cli.flags.from,
          session: cli.flags.session,
          maxContext: cli.flags.maxContext,
          // `--no-tui` arrives as `tui: false` via meow's negation; we also
          // accept an explicit `--no-tui` (= `noTui: true`) as a courtesy.
          noTui: cli.flags.noTui === true || cli.flags.tui === false,
        },
      });
    }
    case "corpus": {
      if ((subcommand === undefined || subcommand === "help") && isHelpFlag()) {
        process.stdout.write(CORPUS_HELP);
        return 0;
      }
      // `corpus <subcmd> <positional>` — e.g. `corpus show <run-id>`.
      const positional = cli.input[2];
      return runCorpus({
        subcommand,
        positional,
        flags: {
          archiveRoot: cli.flags.archiveRoot,
          out: cli.flags.out,
          includeLogs: cli.flags.includeLogs,
          phases: cli.flags.phases,
          olderThan: cli.flags.olderThan,
          // meow translates `--no-dry-run` to `dryRun: false`; pass through.
          dryRun: cli.flags.dryRun,
          unsafeIncludeFindings: cli.flags.unsafeIncludeFindings,
          force: cli.flags.force,
        },
        helpRequested: isHelpFlag(),
      });
    }
    case "help":
    case "--help":
    case "-h":
      cli.showHelp(0);
      return 0;
    default:
      console.error(`Unknown command: ${command}`);
      cli.showHelp(1);
      return 1;
  }
}

run().then((code) => {
  process.exit(code);
});
