// React Query hooks for the Findings API.
//
// Two hooks:
//   - useFindings(runId, query) — list, includes the `meta.data_source`
//     so the page can show the v0 banner without a second fetch
//   - useFinding(runId, propertyId) — detail
//
// Query keys include the query object so filter changes invalidate the
// cache. The backend list is already filtered server-side so we could
// dodge re-fetching, but we keep round trips honest for v0 — the dataset
// is small and the freshness gain outweighs the saved request.

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { apiFetch } from "../../lib/api";

import type {
  Finding,
  FindingQuery,
  FindingsResponse,
} from "./types";

function buildQuery(query: FindingQuery): string {
  const params = new URLSearchParams();
  if (query.phase) params.set("phase", query.phase);
  if (query.severity) params.set("severity", query.severity);
  if (query.verdict) params.set("verdict", query.verdict);
  if (query.target) params.set("target", query.target);
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function useFindings(
  runId: string | undefined,
  query: FindingQuery,
): UseQueryResult<FindingsResponse, Error> {
  return useQuery<FindingsResponse, Error>({
    enabled: Boolean(runId),
    queryKey: ["findings", runId, query],
    queryFn: () =>
      apiFetch<FindingsResponse>(
        `runs/${encodeURIComponent(runId ?? "")}/findings${buildQuery(query)}`,
      ),
  });
}

export function useFinding(
  runId: string | undefined,
  propertyId: string | undefined,
  // Client/target to disambiguate — property ids are spec-derived and
  // repeat across clients in a multi-client audit, so the detail fetch
  // must pin the client the user clicked.
  target?: string,
): UseQueryResult<Finding, Error> {
  return useQuery<Finding, Error>({
    enabled: Boolean(runId && propertyId),
    queryKey: ["finding", runId, propertyId, target ?? null],
    queryFn: () =>
      apiFetch<Finding>(
        `runs/${encodeURIComponent(runId ?? "")}/findings/${encodeURIComponent(propertyId ?? "")}${
          target ? `?target=${encodeURIComponent(target)}` : ""
        }`,
      ),
  });
}
