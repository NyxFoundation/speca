import { describe, expect, it } from "vitest";
import {
  isProviderId,
  PROVIDER_IDS,
  PROVIDERS,
  validateRuntime,
} from "../src/lib/providers/registry.js";

/**
 * ProviderRegistry (issue #113) — CLI-side provider ids + credential checks.
 * The id set must mirror scripts/orchestrator/runtime_registry.py.
 */

describe("provider id set", () => {
  it("matches the Python runtime registry ids", () => {
    expect([...PROVIDER_IDS]).toEqual(["claude", "api", "codex", "gemini", "ollama", "copilot"]);
  });

  it("every id has a descriptor with a matching id field", () => {
    for (const id of PROVIDER_IDS) {
      expect(PROVIDERS[id]?.id).toBe(id);
      expect(PROVIDERS[id]?.summary.length).toBeGreaterThan(0);
    }
  });

  it("isProviderId narrows correctly", () => {
    expect(isProviderId("ollama")).toBe(true);
    expect(isProviderId("claude")).toBe(true);
    expect(isProviderId("gpt5")).toBe(false);
    expect(isProviderId("")).toBe(false);
  });
});

describe("validateRuntime — unknown ids", () => {
  it("rejects an unknown runtime and lists the known ones", () => {
    const r = validateRuntime("bogus", {});
    expect(r.ok).toBe(false);
    expect(r.messages.join("\n")).toContain("unknown runtime 'bogus'");
    expect(r.messages.join("\n")).toContain("ollama");
  });
});

describe("validateRuntime — ollama (cloud vs self-hosted)", () => {
  it("cloud default host requires OLLAMA_API_KEY", () => {
    const r = validateRuntime("ollama", {});
    expect(r.ok).toBe(false);
    expect(r.messages.join("\n")).toContain("OLLAMA_API_KEY");
  });

  it("cloud host with OLLAMA_API_KEY passes", () => {
    const r = validateRuntime("ollama", { OLLAMA_API_KEY: "sk-test" });
    expect(r.ok).toBe(true);
  });

  it("explicit ollama.com host still requires the key", () => {
    const r = validateRuntime("ollama", { OLLAMA_HOST: "https://ollama.com" });
    expect(r.ok).toBe(false);
  });

  it("self-hosted host needs no key", () => {
    const r = validateRuntime("ollama", { OLLAMA_HOST: "http://localhost:11434" });
    expect(r.ok).toBe(true);
  });

  it("empty OLLAMA_HOST falls back to the cloud default", () => {
    const r = validateRuntime("ollama", { OLLAMA_HOST: "  " });
    expect(r.ok).toBe(false);
    expect(r.messages.join("\n")).toContain("OLLAMA_API_KEY");
  });
});

describe("validateRuntime — API-key providers", () => {
  it.each([
    ["api", "API_RUNNER_API_KEY"],
    ["codex", "OPENAI_API_KEY"],
    ["gemini", "GEMINI_API_KEY"],
  ] as const)("%s requires %s", (id, envVar) => {
    const missing = validateRuntime(id, {});
    expect(missing.ok).toBe(false);
    expect(missing.messages.join("\n")).toContain(envVar);

    const present = validateRuntime(id, { [envVar]: "key" });
    expect(present.ok).toBe(true);
  });

  it("whitespace-only keys are treated as missing", () => {
    const r = validateRuntime("codex", { OPENAI_API_KEY: "   " });
    expect(r.ok).toBe(false);
  });
});

describe("validateRuntime — CLI-managed providers", () => {
  it.each([["claude"], ["copilot"]] as const)("%s needs no env credentials", (id) => {
    expect(validateRuntime(id, {}).ok).toBe(true);
  });
});
