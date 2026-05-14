// React Query hooks for the runtime-preferences API.
//
// Two endpoints:
//
//   GET  /api/runtime          → RuntimeView
//   PUT  /api/runtime          → RuntimeView (PATCH semantics — every
//                                 field is optional)
//
// Server state lives under the `['runtime']` query key. Mutations
// invalidate it so the SPA always shows the canonical post-write state.

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";

export type RuntimeId = "claude" | "codex" | "gemini" | "ollama" | "copilot";

export interface RuntimeView {
  runtime: RuntimeId;
  ollama_host: string;
  claude_model: string | null;
  codex_model: string | null;
  gemini_model: string | null;
  ollama_model: string | null;
  codex_cli_available: boolean;
  codex_logged_in: boolean;
  gemini_cli_available: boolean;
  gemini_api_key_present: boolean;
  copilot_cli_available: boolean;
  ollama_api_key_present: boolean;
}

export interface RuntimeUpdate {
  runtime?: RuntimeId;
  ollama_host?: string;
  claude_model?: string | null;
  codex_model?: string | null;
  gemini_model?: string | null;
  ollama_model?: string | null;
}

export const runtimeQueryKey = ["runtime"] as const;

export function useRuntime(): UseQueryResult<RuntimeView> {
  return useQuery<RuntimeView>({
    queryKey: runtimeQueryKey,
    queryFn: () => apiFetch<RuntimeView>("/runtime"),
  });
}

export function useUpdateRuntime(): UseMutationResult<
  RuntimeView,
  Error,
  RuntimeUpdate
> {
  const queryClient = useQueryClient();
  return useMutation<RuntimeView, Error, RuntimeUpdate>({
    mutationFn: (body) =>
      apiFetch<RuntimeView>("/runtime", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(runtimeQueryKey, data);
      queryClient.invalidateQueries({ queryKey: runtimeQueryKey });
    },
  });
}
