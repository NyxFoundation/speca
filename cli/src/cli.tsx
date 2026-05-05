#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { render } from "ink";
import meow from "meow";
import { createElement } from "react";
import { AskCommand } from "./commands/ask.js";
import { BrowseCommand } from "./commands/browse.js";
import { LOGIN_HELP, loginCommand } from "./commands/auth/login.js";
import { StatusCommand } from "./commands/auth/status.js";
import { DoctorCommand } from "./commands/doctor.js";
import { initCommand } from "./commands/init.js";
import { RunCommand } from "./commands/run.js";
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
    init               Set up a new SPECA project (writes TARGET_INFO + scope)
    run                Launch pipeline with live dashboard
    browse             Browse findings (interactive table + detail view)
    ask                Ask Claude about a finding (interactive chat)
    version            Print speca-cli version
    doctor             Check Node / uv / git / claude-code / auth status
    auth <subcommand>  Manage Anthropic credentials (login | status)
    help               Print this help

  Run flags
    --phase <ids...>   Run specific phases (e.g. --phase 01a 01b)
    --target <id>      Run all phases up to target (resolves deps)
    --workers <n>      Number of parallel workers (default: 4)
    --max-concurrent <n>  Max concurrent tasks per worker
    --force            Force re-execution (bypass resume)

  Common flags
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
`,
  {
    importMeta: import.meta,
    flags: {
      noTui: { type: "boolean", default: false },
      json: { type: "boolean", default: false },
      apiKey: { type: "string" },
      mode: { type: "string" },
      phase: { type: "string", isMultiple: true },
      target: { type: "string" },
      workers: { type: "number" },
      maxConcurrent: { type: "number" },
      force: { type: "boolean", default: false },
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
    case "init":
      return initCommand();
    case "run": {
      const app = render(
        createElement(RunCommand, {
          phases: cli.flags.phase && cli.flags.phase.length > 0 ? cli.flags.phase : undefined,
          target: cli.flags.target,
          workers: cli.flags.workers,
          maxConcurrent: cli.flags.maxConcurrent,
          force: cli.flags.force || undefined,
        }),
      );
      await app.waitUntilExit();
      return 0;
    }
    case "browse": {
      const app = render(createElement(BrowseCommand, {}));
      await app.waitUntilExit();
      return 0;
    }
    case "ask": {
      const app = render(createElement(AskCommand, {}));
      await app.waitUntilExit();
      return 0;
    }
    case "auth":
      return runAuth();
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
