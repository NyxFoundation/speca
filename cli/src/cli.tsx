#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { render } from "ink";
import meow from "meow";
import { createElement } from "react";
import { printAskHelp, runAskCommand } from "./commands/ask.js";
import { LOGIN_HELP, loginCommand } from "./commands/auth/login.js";
import { StatusCommand } from "./commands/auth/status.js";
import { DoctorCommand } from "./commands/doctor.js";
import { VersionCommand } from "./commands/version.js";

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
    ask [finding-id]   Chat with Claude about a finding (claude-code session)
    help               Print this help

  Common flags (reserved for future milestones)
    --no-tui           Force plain-text output (M6)
    --json             Emit machine-readable events on stdout (M3)

  Auth-specific flags (only consumed under 'auth login')
    --api-key <key>    Skip OAuth and persist an Anthropic API key
    --mode <max|console>
                       OAuth entitlement source (default: max)

  Ask-specific flags
    --from <file>      PARTIAL JSON file containing the finding
    --session <id>     Resume an existing chat session
    --max-context <n>  Context cap in bytes (default 50000)

  Examples
    $ speca doctor
    $ speca version
    $ speca auth status
    $ speca auth login
    $ speca auth login --api-key sk-ant-api03-...
    $ speca ask --from outputs/04_PARTIAL_W0B0.json finding-001
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
      apiKey: { type: "string" },
      mode: { type: "string" },
      // `speca ask` flags (ignored by other commands)
      from: { type: "string" },
      session: { type: "string" },
      maxContext: { type: "number" },
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
      const mode = cli.flags.mode;
      if (mode !== undefined && mode !== "max" && mode !== "console") {
        process.stderr.write(`Invalid --mode value: ${mode}. Expected "max" or "console".\n`);
        return 1;
      }
      return loginCommand({
        apiKey: cli.flags.apiKey,
        mode: mode as "max" | "console" | undefined,
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
    case "ask": {
      const wantsHelp = subcommand === "help" || isHelpFlag();
      if (wantsHelp) {
        printAskHelp();
        return 0;
      }
      const positional = cli.input.slice(1);
      return runAskCommand({
        positional,
        flags: {
          from: cli.flags.from,
          session: cli.flags.session,
          maxContext: cli.flags.maxContext,
          noTui: cli.flags.noTui === true || cli.flags.tui === false,
        },
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
