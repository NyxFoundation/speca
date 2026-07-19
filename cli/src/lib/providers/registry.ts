/**
 * ProviderRegistry — CLI-side model-provider selection for `speca run`
 * (issue #113: use ollama cloud as a claude alternative).
 *
 * Split of responsibilities per #113:
 *   - The CLI (this module) owns what can be checked BEFORE spawning the
 *     orchestrator: which providers exist, and whether the environment
 *     carries the credentials each one needs. Fail fast with an actionable
 *     message instead of letting the first batch die mid-pipeline.
 *   - The Python side owns LLM execution: `scripts/orchestrator/
 *     runtime_registry.py` maps the same ids to runner classes
 *     (ClaudeRunner / APIRunner subclasses / CopilotRunner). The id set
 *     below MUST stay in sync with that registry — `speca run --runtime X`
 *     is forwarded verbatim as `run_phase.py --runtime X`.
 *
 * Adding a provider = one entry here (credential rules) + a runner on the
 * Python side. Nothing else in the CLI needs to change.
 */

export const PROVIDER_IDS = ["claude", "api", "codex", "gemini", "ollama", "copilot"] as const;
export type ProviderId = (typeof PROVIDER_IDS)[number];

export interface ProviderValidation {
  ok: boolean;
  /** Human-readable lines: what is missing and how to fix it. */
  messages: string[];
}

export interface ProviderDescriptor {
  id: ProviderId;
  /** One-line description for help/error output. */
  summary: string;
  /** Check `env` for the credentials this provider needs. */
  validate(env: NodeJS.ProcessEnv): ProviderValidation;
}

const OLLAMA_DEFAULT_HOST = "https://ollama.com";

/**
 * True when `host` points at ollama cloud (ollama.com or a subdomain).
 *
 * A substring test (`host.includes("ollama.com")`) misfires on hosts like
 * `myollama.company.com` or URLs that merely mention ollama.com in a query
 * string, so parse the hostname and compare label-wise. Kept in sync with
 * `is_ollama_cloud_host` in scripts/orchestrator/runtime_registry.py — an
 * unparseable host counts as self-hosted on both sides (the runner will
 * surface the real error).
 */
export function isOllamaCloudHost(host: string): boolean {
  let raw = host.trim();
  if (raw === "") raw = OLLAMA_DEFAULT_HOST;
  if (!raw.includes("://")) raw = `http://${raw}`;
  let hostname: string;
  try {
    hostname = new URL(raw).hostname.toLowerCase();
  } catch {
    return false;
  }
  return hostname === "ollama.com" || hostname.endsWith(".ollama.com");
}

function ok(): ProviderValidation {
  return { ok: true, messages: [] };
}

function requireEnv(env: NodeJS.ProcessEnv, name: string, hint: string): ProviderValidation {
  const value = env[name];
  if (value !== undefined && value.trim() !== "") return ok();
  return { ok: false, messages: [`${name} is not set. ${hint}`] };
}

export const PROVIDERS: Record<ProviderId, ProviderDescriptor> = {
  claude: {
    id: "claude",
    summary: "Anthropic claude CLI (default). Auth is managed by `claude auth login`.",
    // The claude CLI owns its credential store; `speca run` already has a
    // dedicated expired-auth pre-flight for it.
    validate: () => ok(),
  },
  api: {
    id: "api",
    summary: "OpenRouter-style OpenAI-compatible HTTP endpoint.",
    validate: (env) =>
      requireEnv(env, "API_RUNNER_API_KEY", "Export an OpenRouter (or compatible) API key."),
  },
  codex: {
    id: "codex",
    summary: "OpenAI Chat API (codex).",
    validate: (env) => requireEnv(env, "OPENAI_API_KEY", "Export an OpenAI API key."),
  },
  gemini: {
    id: "gemini",
    summary: "Google Gemini via its OpenAI compatibility endpoint.",
    validate: (env) =>
      requireEnv(env, "GEMINI_API_KEY", "Export a Google AI Studio API key."),
  },
  ollama: {
    id: "ollama",
    summary: "Ollama cloud (ollama.com) or a self-hosted Ollama server.",
    validate: (env) => {
      // Mirrors scripts/orchestrator/runtime_registry.py::_probe_ollama —
      // cloud hosts need OLLAMA_API_KEY; self-hosted (localhost etc.) do not.
      const host = (env["OLLAMA_HOST"] ?? OLLAMA_DEFAULT_HOST).trim() || OLLAMA_DEFAULT_HOST;
      const cloud = isOllamaCloudHost(host);
      if (!cloud) return ok();
      return requireEnv(
        env,
        "OLLAMA_API_KEY",
        `Host ${host} is ollama cloud — create a key at https://ollama.com/settings/keys, ` +
          "or point OLLAMA_HOST at a self-hosted server (e.g. http://localhost:11434).",
      );
    },
  },
  copilot: {
    id: "copilot",
    summary: "GitHub Copilot agentic CLI. Auth via `copilot` interactive OAuth.",
    validate: () => ok(),
  },
};

export function isProviderId(value: string): value is ProviderId {
  return (PROVIDER_IDS as readonly string[]).includes(value);
}

/**
 * Validate `runtime` against the registry + environment.
 *
 * Returns `ok: false` with ready-to-print stderr lines for an unknown id
 * or missing credentials; the caller exits before spawning the pipeline.
 */
export function validateRuntime(
  runtime: string,
  env: NodeJS.ProcessEnv = process.env,
): ProviderValidation {
  if (!isProviderId(runtime)) {
    return {
      ok: false,
      messages: [
        `unknown runtime '${runtime}'. Known runtimes: ${PROVIDER_IDS.join(", ")}.`,
      ],
    };
  }
  const result = PROVIDERS[runtime].validate(env);
  if (result.ok) return result;
  return {
    ok: false,
    messages: [
      `runtime '${runtime}' is not usable with the current environment:`,
      ...result.messages.map((m) => `  - ${m}`),
    ],
  };
}
