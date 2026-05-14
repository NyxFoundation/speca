/**
 * `speca corpus list` — table view of every run under `.speca/runs/`.
 *
 * Read-only. Renders the same RunSummary rows from `lib/corpus/runs.ts`
 * sorted desc by startedAt. Unreadable rows fall to the bottom with a
 * `unreadable` status so partial/aborted archives are still visible
 * (otherwise the operator has no signal that the run dir exists at all).
 */
import { Box, Text, useApp } from "ink";
import { useEffect, useState } from "react";

import { Layout } from "../../components/Layout.js";
import { archiveRoot } from "../../lib/corpus/paths.js";
import { listRuns } from "../../lib/corpus/runs.js";
import type { RunSummary } from "../../lib/corpus/manifest.js";

interface CorpusListCommandProps {
  /** Override the archive root (used by tests). */
  archiveRootOverride?: string;
  /** Inject "now" for deterministic snapshots. */
  now?: number;
}

function formatCost(usd: number): string {
  if (usd === 0) return "—";
  if (usd < 0.01) return `$<0.01`;
  return `$${usd.toFixed(2)}`;
}

function formatStartedAt(s: string): string {
  // run-ids embed the start time as YYYY-MM-DDTHH-MM-SSZ; for table use we
  // present it in the same shape so users can copy/paste to query show.
  // started_at on the manifest is ISO with colons — display as-is.
  if (!s) return "—";
  // Trim subseconds for compactness.
  return s.replace(/\.\d+/, "").replace(/T/, " ").replace(/Z$/, "");
}

function statusGlyph(status: RunSummary["status"], unreadable: boolean): { text: string; color: string } {
  if (unreadable) return { text: "broken ", color: "yellow" };
  switch (status) {
    case "ok":
      return { text: "ok     ", color: "green" };
    case "error":
      return { text: "error  ", color: "red" };
    case "pending":
      return { text: "pending", color: "yellow" };
    default:
      return { text: "unknown", color: "gray" };
  }
}

const HEADERS = ["status", "started_at", "phases", "cost", "run_id"];

export function CorpusListCommand({ archiveRootOverride }: CorpusListCommandProps = {}) {
  const { exit } = useApp();
  const [rows, setRows] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resolvedRoot, setResolvedRoot] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    const root = archiveRoot(archiveRootOverride);
    setResolvedRoot(root);
    listRuns(root)
      .then((rs) => {
        if (cancelled) return;
        setRows(rs);
        setTimeout(() => exit(undefined), 30);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError((err as Error).message);
        setTimeout(() => exit(new Error("corpus list: failed")), 30);
      });
    return () => {
      cancelled = true;
    };
  }, [archiveRootOverride, exit]);

  if (error) {
    return (
      <Layout title="speca corpus list" status={`error: ${error}`}>
        <Text color="red">Failed to read archive root.</Text>
      </Layout>
    );
  }

  if (rows === null) {
    return (
      <Layout title="speca corpus list" status="Reading archive...">
        <Text dimColor>Scanning {resolvedRoot}...</Text>
      </Layout>
    );
  }

  if (rows.length === 0) {
    return (
      <Layout title="speca corpus list" status={`Archive root: ${resolvedRoot}`}>
        <Text dimColor>
          No runs found. Either the archive root is empty or you haven't
          executed a `speca run` / `uv run python scripts/run_phase.py` yet.
        </Text>
      </Layout>
    );
  }

  return (
    <Layout
      title="speca corpus list"
      status={`${rows.length} run(s) at ${resolvedRoot}`}
    >
      <Box flexDirection="row" marginBottom={1}>
        <Box width={9}>
          <Text bold>{HEADERS[0]}</Text>
        </Box>
        <Box width={22}>
          <Text bold>{HEADERS[1]}</Text>
        </Box>
        <Box width={20}>
          <Text bold>{HEADERS[2]}</Text>
        </Box>
        <Box width={10}>
          <Text bold>{HEADERS[3]}</Text>
        </Box>
        <Box>
          <Text bold>{HEADERS[4]}</Text>
        </Box>
      </Box>
      {rows.map((row) => {
        const glyph = statusGlyph(row.status, row.unreadable);
        return (
          <Box key={row.runId} flexDirection="row">
            <Box width={9}>
              <Text color={glyph.color}>{glyph.text}</Text>
            </Box>
            <Box width={22}>
              <Text>{formatStartedAt(row.startedAt)}</Text>
            </Box>
            <Box width={20}>
              <Text dimColor>
                {row.phasesCompleted.length > 0 ? row.phasesCompleted.join(",") : "—"}
              </Text>
            </Box>
            <Box width={10}>
              <Text>{formatCost(row.costUsdTotal)}</Text>
            </Box>
            <Box>
              <Text dimColor>{row.runId}</Text>
            </Box>
          </Box>
        );
      })}
    </Layout>
  );
}
