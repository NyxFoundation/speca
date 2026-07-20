import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  isOllamaCloudHost,
  isProviderId,
  PROVIDER_IDS,
  PROVIDERS,
  validateRuntime,
} from "../src/lib/providers/registry.js";

/**
 * ProviderRegistry (issue #113) — CLI-side provider ids + credential checks.
 * The id set must mirror scripts/orchestrator/runtime_registry.py.
 */

const HERE = dirname(fileURLToPath(import.meta.url));

/** Ids as declared by the Python registry — parsed from the source of truth,
 * not hand-copied, so a drift on either side fails this suite. */
function pythonRuntimeIds(): string[] {
  const src = readFileSync(
    join(HERE, "..", "..", "scripts", "orchestrator", "runtime_registry.py"),
    "utf8",
  );
  const literal = src.match(/RuntimeId = Literal\[([^\]]+)\]/);
  if (!literal?.[1]) throw new Error("RuntimeId Literal not found in runtime_registry.py");
  return [...literal[1].matchAll(/"([^"]+)"/g)].map((m) => m[1] as string);
}

describe("provider id set", () => {
  it("matches the Python runtime registry ids (parsed from the Python source)", () => {
    expect([...PROVIDER_IDS]).toEqual(pythonRuntimeIds());
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

describe("isOllamaCloudHost — hostname parsing (not substring matching)", () => {
  it.each([
    ["https://ollama.com", true],
    ["ollama.com", true],
    ["https://api.ollama.com", true],
    ["OLLAMA.COM", true],
    ["http://localhost:11434", false],
    ["192.168.1.10:11434", false],
    // Substring misfires the old `includes("ollama.com")` check got wrong:
    ["https://myollama.company.com", false],
    ["myollama.company.com:11434", false],
    ["https://example.com/?redirect=ollama.com", false],
    // Suffix-spoof must not count as cloud:
    ["https://evilollama.com.attacker.net", false],
    ["", true], // empty falls back to the cloud default host
    ["not a parseable host", false], // unparseable counts as self-hosted
    // Scheme-relative hosts must classify the same as the Python side:
    ["//ollama.com", true],
    ["//api.ollama.com", true],
    ["//myollama.company.com", false],
    ["//localhost:11434", false],
  ])("%s -> cloud=%s", (host, expected) => {
    expect(isOllamaCloudHost(host)).toBe(expected);
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

  it("a self-hosted host that merely CONTAINS ollama.com needs no key", () => {
    const r = validateRuntime("ollama", { OLLAMA_HOST: "https://myollama.company.com" });
    expect(r.ok).toBe(true);
  });

  it("an ollama.com subdomain is cloud and requires the key", () => {
    const r = validateRuntime("ollama", { OLLAMA_HOST: "https://api.ollama.com" });
    expect(r.ok).toBe(false);
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
  it.each([["claude"], ["copilot"], ["claude_pty"]] as const)(
    "%s needs no env credentials",
    (id) => {
      expect(validateRuntime(id, {}).ok).toBe(true);
    },
  );
});
