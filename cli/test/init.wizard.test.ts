import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { runInitCommand } from "../src/commands/init.js";
import { buildArtefacts } from "../src/lib/init/build.js";
import {
  validateBugBountyScope,
  validateTargetInfo,
} from "../src/lib/schemas/index.js";
import {
  TARGET_LANGUAGES,
  TARGET_LAYERS,
  validateProjectName,
  validateTargetRepo,
} from "../src/lib/init/types.js";
import {
  WizardCancelled,
  WizardMissingInput,
  buildAnswersNonInteractive,
  runInteractiveWizard,
} from "../src/lib/init/wizard.js";

let tmpRoot: string;

beforeEach(() => {
  tmpRoot = mkdtempSync(join(tmpdir(), "speca-init-"));
});

afterEach(() => {
  rmSync(tmpRoot, { recursive: true, force: true });
});

describe("validateTargetRepo", () => {
  it("accepts canonical github URLs", () => {
    expect(validateTargetRepo("https://github.com/foo/bar")).toBeUndefined();
    expect(validateTargetRepo("https://github.com/sigp/lighthouse")).toBeUndefined();
    expect(validateTargetRepo("https://github.com/ethereum/go-ethereum.git")).toBeUndefined();
  });
  it("rejects empty / wrong-host URLs", () => {
    expect(validateTargetRepo("")).toMatch(/required/);
    expect(validateTargetRepo("git@github.com:foo/bar.git")).toMatch(/github/);
    expect(validateTargetRepo("https://gitlab.com/foo/bar")).toMatch(/github/);
  });
});

describe("validateProjectName", () => {
  it("accepts plain identifiers", () => {
    expect(validateProjectName("my-project")).toBeUndefined();
    expect(validateProjectName("my.project_1")).toBeUndefined();
  });
  it("rejects empty or weird names", () => {
    expect(validateProjectName("")).toMatch(/required/);
    expect(validateProjectName("with spaces")).toBeDefined();
    expect(validateProjectName("/etc/passwd")).toBeDefined();
  });
});

describe("buildArtefacts", () => {
  it("produces TARGET_INFO that satisfies the U2 schema", () => {
    const { targetInfo } = buildArtefacts({
      projectName: "lighthouse",
      targetRepo: "https://github.com/sigp/lighthouse",
      targetCommit: "HEAD",
      targetLanguage: "Rust",
      targetLayer: "consensus",
      rubricMode: "default",
      outputDir: tmpRoot,
    });
    const result = validateTargetInfo(targetInfo);
    expect(result.ok).toBe(true);
    expect(targetInfo.target_repo).toBe("https://github.com/sigp/lighthouse");
    expect(targetInfo.target_ref_label).toBe("HEAD");
  });

  it("produces BUG_BOUNTY_SCOPE that satisfies the U2 schema (default rubric)", () => {
    const { bugBountyScope } = buildArtefacts({
      projectName: "demo",
      targetRepo: "https://github.com/foo/bar",
      targetCommit: "HEAD",
      targetLanguage: "Solidity",
      targetLayer: "smart-contract",
      rubricMode: "default",
      outputDir: tmpRoot,
    });
    const result = validateBugBountyScope(bugBountyScope);
    expect(result.ok).toBe(true);
    expect(bugBountyScope.severity_classification).toBeDefined();
    const sevs = bugBountyScope.severity_classification as Record<string, unknown>;
    expect(Object.keys(sevs)).toContain("Critical");
    expect(Object.keys(sevs)).toContain("Informational");
  });

  it("produces BUG_BOUNTY_SCOPE for custom mode with edit-me hints", () => {
    const { bugBountyScope } = buildArtefacts({
      projectName: "demo",
      targetRepo: "https://github.com/foo/bar",
      targetCommit: "HEAD",
      targetLanguage: "Solidity",
      targetLayer: "smart-contract",
      rubricMode: "custom",
      outputDir: tmpRoot,
    });
    const result = validateBugBountyScope(bugBountyScope);
    expect(result.ok).toBe(true);
    expect(JSON.stringify(bugBountyScope.scope_notes)).toMatch(/TODO/);
  });

  it("encodes non-HEAD commit refs as commit-type", () => {
    const { targetInfo } = buildArtefacts({
      projectName: "demo",
      targetRepo: "https://github.com/foo/bar",
      targetCommit: "abc1234",
      targetLanguage: "Go",
      targetLayer: "execution",
      rubricMode: "default",
      outputDir: tmpRoot,
    });
    expect(targetInfo.target_ref_type).toBe("commit");
    expect(targetInfo.target_commit).toBe("abc1234");
  });
});

describe("buildAnswersNonInteractive", () => {
  it("requires target-repo / target-language / target-layer", () => {
    expect(() => buildAnswersNonInteractive({})).toThrow(WizardMissingInput);
    expect(() =>
      buildAnswersNonInteractive({ targetRepo: "https://github.com/foo/bar" }),
    ).toThrow(WizardMissingInput);
    expect(() =>
      buildAnswersNonInteractive({
        targetRepo: "https://github.com/foo/bar",
        targetLanguage: "Solidity",
      }),
    ).toThrow(WizardMissingInput);
  });

  it("rejects unknown languages and layers", () => {
    expect(() =>
      buildAnswersNonInteractive({
        targetRepo: "https://github.com/foo/bar",
        targetLanguage: "Klingon" as unknown as (typeof TARGET_LANGUAGES)[number],
        targetLayer: "smart-contract",
      }),
    ).toThrow(WizardMissingInput);
    expect(() =>
      buildAnswersNonInteractive({
        targetRepo: "https://github.com/foo/bar",
        targetLanguage: "Solidity",
        targetLayer: "moon-rover" as unknown as (typeof TARGET_LAYERS)[number],
      }),
    ).toThrow(WizardMissingInput);
  });

  it("fills sensible defaults when optional flags are missing", () => {
    const answers = buildAnswersNonInteractive({
      targetRepo: "https://github.com/foo/bar",
      targetLanguage: "Solidity",
      targetLayer: "smart-contract",
      projectName: "explicit-name",
    });
    expect(answers.targetCommit).toBe("HEAD");
    expect(answers.rubricMode).toBe("default");
    expect(answers.outputDir).toBeTruthy();
    expect(answers.projectName).toBe("explicit-name");
  });
});

describe("runInteractiveWizard with stubbed prompts", () => {
  it("collects answers from stubbed clack prompts", async () => {
    const prompts = {
      promptText: vi
        .fn()
        // projectName
        .mockResolvedValueOnce("demo-project")
        // targetRepo
        .mockResolvedValueOnce("https://github.com/foo/bar")
        // targetCommit
        .mockResolvedValueOnce("HEAD")
        // outputDir (asked last)
        .mockResolvedValueOnce(tmpRoot),
      promptSelect: vi
        .fn()
        // language
        .mockResolvedValueOnce("Rust")
        // layer
        .mockResolvedValueOnce("execution")
        // rubric
        .mockResolvedValueOnce("default"),
      intro: vi.fn(),
      outro: vi.fn(),
      note: vi.fn(),
    } as Parameters<typeof runInteractiveWizard>[1];

    const answers = await runInteractiveWizard({}, prompts);
    expect(answers.projectName).toBe("demo-project");
    expect(answers.targetRepo).toBe("https://github.com/foo/bar");
    expect(answers.targetCommit).toBe("HEAD");
    expect(answers.targetLanguage).toBe("Rust");
    expect(answers.targetLayer).toBe("execution");
    expect(answers.rubricMode).toBe("default");
    expect(answers.outputDir).toBe(tmpRoot);
  });

  it("propagates clack cancellation as WizardCancelled", async () => {
    // The real clack uses a private Symbol("clack:cancel") that isCancel()
    // identity-checks. We can't construct it from outside, but we can grab a
    // canonical cancel value by aborting an actual prompt with an
    // already-aborted AbortController.
    const clack = await import("@clack/prompts");
    const ctl = new AbortController();
    ctl.abort();
    const cancelValue = await clack.text({
      message: "ignored",
      signal: ctl.signal,
    });
    expect(clack.isCancel(cancelValue)).toBe(true);

    const prompts = {
      promptText: vi.fn().mockResolvedValueOnce(cancelValue),
      promptSelect: vi.fn(),
      intro: vi.fn(),
      outro: vi.fn(),
      note: vi.fn(),
    } as Parameters<typeof runInteractiveWizard>[1];
    await expect(runInteractiveWizard({}, prompts)).rejects.toBeInstanceOf(WizardCancelled);
  });

  it("respects override flags so prompts are not asked for those fields", async () => {
    const promptText = vi
      .fn()
      // only targetCommit and outputDir should be prompted (projectName, targetRepo provided)
      .mockResolvedValueOnce("HEAD")
      .mockResolvedValueOnce(tmpRoot);
    const promptSelect = vi
      .fn()
      .mockResolvedValueOnce("Rust")
      .mockResolvedValueOnce("execution")
      .mockResolvedValueOnce("default");
    const prompts = {
      promptText,
      promptSelect,
      intro: vi.fn(),
      outro: vi.fn(),
      note: vi.fn(),
    } as Parameters<typeof runInteractiveWizard>[1];

    const answers = await runInteractiveWizard(
      {
        projectName: "preset",
        targetRepo: "https://github.com/foo/bar",
      },
      prompts,
    );
    expect(answers.projectName).toBe("preset");
    expect(answers.targetRepo).toBe("https://github.com/foo/bar");
    expect(promptText).toHaveBeenCalledTimes(2);
  });
});

describe("runInitCommand (non-interactive)", () => {
  it("writes valid TARGET_INFO and BUG_BOUNTY_SCOPE under the chosen output dir", async () => {
    const code = await runInitCommand({
      flags: {
        targetRepo: "https://github.com/foo/bar",
        targetLanguage: "Solidity",
        targetLayer: "smart-contract",
        rubric: "default",
        outputDir: tmpRoot,
        nonInteractive: true,
      },
      log: () => undefined,
      errorLog: () => undefined,
    });
    expect(code).toBe(0);

    const ti = JSON.parse(readFileSync(join(tmpRoot, "TARGET_INFO.json"), "utf8"));
    const bb = JSON.parse(readFileSync(join(tmpRoot, "BUG_BOUNTY_SCOPE.json"), "utf8"));
    expect(validateTargetInfo(ti).ok).toBe(true);
    expect(validateBugBountyScope(bb).ok).toBe(true);
    expect(ti.target_repo).toBe("https://github.com/foo/bar");
    expect(bb.program_name).toContain("ethereum.org");
  });

  it("errors out (exit 2) when required fields are missing in non-interactive mode", async () => {
    const code = await runInitCommand({
      flags: {
        nonInteractive: true,
      },
      log: () => undefined,
      errorLog: () => undefined,
    });
    expect(code).toBe(2);
  });

  it("refuses to overwrite existing files without --force in non-interactive mode", async () => {
    mkdirSync(tmpRoot, { recursive: true });
    writeFileSync(join(tmpRoot, "TARGET_INFO.json"), "{}");
    const code = await runInitCommand({
      flags: {
        targetRepo: "https://github.com/foo/bar",
        targetLanguage: "Solidity",
        targetLayer: "smart-contract",
        rubric: "default",
        outputDir: tmpRoot,
        nonInteractive: true,
      },
      log: () => undefined,
      errorLog: () => undefined,
    });
    expect(code).toBe(2);
    // file untouched
    expect(readFileSync(join(tmpRoot, "TARGET_INFO.json"), "utf8")).toBe("{}");
  });

  it("--force overwrites existing files", async () => {
    mkdirSync(tmpRoot, { recursive: true });
    writeFileSync(join(tmpRoot, "TARGET_INFO.json"), "{}");
    writeFileSync(join(tmpRoot, "BUG_BOUNTY_SCOPE.json"), "{}");
    const code = await runInitCommand({
      flags: {
        targetRepo: "https://github.com/foo/bar",
        targetLanguage: "Go",
        targetLayer: "execution",
        rubric: "default",
        outputDir: tmpRoot,
        nonInteractive: true,
        force: true,
      },
      log: () => undefined,
      errorLog: () => undefined,
    });
    expect(code).toBe(0);
    const ti = JSON.parse(readFileSync(resolve(join(tmpRoot, "TARGET_INFO.json")), "utf8"));
    expect(ti.target_repo).toBe("https://github.com/foo/bar");
  });
});
