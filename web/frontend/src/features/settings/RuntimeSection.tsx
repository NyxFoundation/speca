// SettingsPage runtime selector — 5-way switch + per-runtime model /
// host fields + availability hints.
//
// SPECA web ships with five chat backends:
//
//   * claude  — Anthropic. Uses SDK for API keys, claude CLI subprocess
//               for claude.ai OAuth subscribers.
//   * codex   — OpenAI's codex CLI (`codex exec --json`).
//   * gemini  — Google's gemini CLI (`gemini -p --output-format stream-json`).
//   * ollama  — Ollama HTTP (cloud or self-hosted via the host field).
//   * copilot — GitHub Copilot via `gh copilot suggest` (read-only,
//               single-shot — no streaming).
//
// Each runtime has a credentials story we do not own (the user runs the
// CLI's own login). The availability badges (✓ / ⚠) come from the
// backend `/api/runtime` endpoint and tell the user whether their
// chosen runtime is wired up.

import { useEffect, useState, type ChangeEvent, type ReactElement } from "react";

import { useT } from "@/i18n/useT";

import {
  useRuntime,
  useUpdateRuntime,
  type RuntimeId,
  type RuntimeView,
} from "./useRuntime";
import styles from "./SettingsPage.module.css";

const RUNTIMES: RuntimeId[] = ["claude", "codex", "gemini", "ollama", "copilot"];

function availabilityFor(
  runtime: RuntimeId,
  view: RuntimeView,
): { ok: boolean; hintKey: string } {
  switch (runtime) {
    case "claude":
      // The auth router answers the real question; here we just always
      // say "available" because claude is the default fallback.
      return { ok: true, hintKey: "settings.runtime.hint_claude" };
    case "codex":
      if (!view.codex_cli_available)
        return { ok: false, hintKey: "settings.runtime.hint_codex_cli_missing" };
      if (!view.codex_logged_in)
        return { ok: false, hintKey: "settings.runtime.hint_codex_logged_out" };
      return { ok: true, hintKey: "settings.runtime.hint_codex_ready" };
    case "gemini":
      if (!view.gemini_cli_available)
        return { ok: false, hintKey: "settings.runtime.hint_gemini_cli_missing" };
      // Either auth path satisfies us: an API key in the env var, OR a
      // Google ADC token (gcloud auth application-default login +
      // GOOGLE_GENAI_USE_GCA=true). The hint distinguishes the active
      // path so users see how they authenticated.
      if (view.gemini_api_key_present)
        return { ok: true, hintKey: "settings.runtime.hint_gemini_ready_key" };
      if (view.gemini_adc_available)
        return { ok: true, hintKey: "settings.runtime.hint_gemini_ready_adc" };
      return { ok: false, hintKey: "settings.runtime.hint_gemini_auth_missing" };
    case "ollama":
      if (
        view.ollama_host.includes("ollama.com") &&
        !view.ollama_api_key_present
      )
        return { ok: false, hintKey: "settings.runtime.hint_ollama_key_missing" };
      return { ok: true, hintKey: "settings.runtime.hint_ollama_ready" };
    case "copilot":
      if (!view.copilot_cli_available)
        return { ok: false, hintKey: "settings.runtime.hint_copilot_cli_missing" };
      return { ok: true, hintKey: "settings.runtime.hint_copilot_ready" };
  }
}

export function RuntimeSection(): ReactElement {
  const t = useT();
  const { data, isPending, isError } = useRuntime();
  const mutation = useUpdateRuntime();

  // Local copy of the editable fields so typing doesn't trigger a write
  // per keystroke. We push to the server on blur / button click.
  const [ollamaHost, setOllamaHost] = useState("");
  const [claudeModel, setClaudeModel] = useState("");
  const [codexModel, setCodexModel] = useState("");
  const [geminiModel, setGeminiModel] = useState("");
  const [ollamaModel, setOllamaModel] = useState("");

  useEffect(() => {
    if (!data) return;
    setOllamaHost(data.ollama_host);
    setClaudeModel(data.claude_model ?? "");
    setCodexModel(data.codex_model ?? "");
    setGeminiModel(data.gemini_model ?? "");
    setOllamaModel(data.ollama_model ?? "");
  }, [data]);

  if (isPending) {
    return <p className={styles.muted}>{t("settings.runtime.loading")}</p>;
  }
  if (isError || !data) {
    return <p className={styles.muted}>{t("settings.runtime.load_failed")}</p>;
  }

  const selectRuntime = (runtime: RuntimeId) => {
    if (runtime === data.runtime) return;
    mutation.mutate({ runtime });
  };

  const commit = (field: keyof RuntimeView, value: string | null) => {
    const trimmed = typeof value === "string" ? value.trim() : value;
    const current = (data as unknown as Record<string, unknown>)[field];
    if (trimmed === current) return;
    // For string fields, treat empty as null on the wire so the backend
    // stores "use the runtime's default" rather than the literal "".
    const payload: Record<string, unknown> = {
      [field]: trimmed === "" ? null : trimmed,
    };
    mutation.mutate(payload);
  };

  return (
    <div className={styles.runtimeSection} data-testid="settings-runtime">
      <div className={styles.runtimeChooser}>
        {RUNTIMES.map((r) => {
          const { ok } = availabilityFor(r, data);
          const active = data.runtime === r;
          return (
            <button
              key={r}
              type="button"
              className={`${styles.runtimeButton} ${
                active ? styles.runtimeButtonActive : ""
              }`}
              onClick={() => selectRuntime(r)}
              aria-pressed={active}
              data-testid={`runtime-pick-${r}`}
            >
              <span className={styles.runtimeButtonLabel}>
                {t(`settings.runtime.runtime_${r}`)}
              </span>
              <span
                className={`${styles.runtimeBadge} ${
                  ok ? styles.runtimeBadgeOk : styles.runtimeBadgeWarn
                }`}
                aria-hidden="true"
              >
                {ok ? "✓" : "!"}
              </span>
            </button>
          );
        })}
      </div>

      <p className={styles.runtimeHint}>
        {t(availabilityFor(data.runtime, data).hintKey)}
      </p>

      <details className={styles.runtimeAdvanced}>
        <summary>{t("settings.runtime.advanced_summary")}</summary>

        <ModelInput
          label={t("settings.runtime.claude_model_label")}
          placeholder={t("settings.runtime.claude_model_placeholder")}
          value={claudeModel}
          onChange={setClaudeModel}
          onCommit={() => commit("claude_model", claudeModel)}
          testid="runtime-claude-model"
        />
        <ModelInput
          label={t("settings.runtime.codex_model_label")}
          placeholder={t("settings.runtime.codex_model_placeholder")}
          value={codexModel}
          onChange={setCodexModel}
          onCommit={() => commit("codex_model", codexModel)}
          testid="runtime-codex-model"
        />
        <ModelInput
          label={t("settings.runtime.gemini_model_label")}
          placeholder={t("settings.runtime.gemini_model_placeholder")}
          value={geminiModel}
          onChange={setGeminiModel}
          onCommit={() => commit("gemini_model", geminiModel)}
          testid="runtime-gemini-model"
        />
        <ModelInput
          label={t("settings.runtime.ollama_host_label")}
          placeholder={t("settings.runtime.ollama_host_placeholder")}
          value={ollamaHost}
          onChange={setOllamaHost}
          onCommit={() => commit("ollama_host", ollamaHost)}
          testid="runtime-ollama-host"
        />
        <ModelInput
          label={t("settings.runtime.ollama_model_label")}
          placeholder={t("settings.runtime.ollama_model_placeholder")}
          value={ollamaModel}
          onChange={setOllamaModel}
          onCommit={() => commit("ollama_model", ollamaModel)}
          testid="runtime-ollama-model"
        />
      </details>

      {mutation.isError ? (
        <p className={styles.error} role="alert">
          {mutation.error?.message ?? t("settings.runtime.save_failed")}
        </p>
      ) : null}
    </div>
  );
}

interface ModelInputProps {
  label: string;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  onCommit: () => void;
  testid: string;
}

function ModelInput({
  label,
  placeholder,
  value,
  onChange,
  onCommit,
  testid,
}: ModelInputProps): ReactElement {
  return (
    <label className={styles.runtimeField}>
      <span className={styles.runtimeFieldLabel}>{label}</span>
      <input
        className={styles.runtimeFieldInput}
        type="text"
        autoComplete="off"
        spellCheck={false}
        value={value}
        placeholder={placeholder}
        onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
        onBlur={onCommit}
        data-testid={testid}
      />
    </label>
  );
}

export default RuntimeSection;
