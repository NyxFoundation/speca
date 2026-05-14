/**
 * `speca corpus show <run-id>` — manifest + per-phase summary.
 *
 * Read-only. Reads `<archiveRoot>/<runId>/manifest.json` and the per-phase
 * directory listings to surface the most useful provenance fields at a
 * glance. Designed to be copy/pasteable into a PR description or issue
 * comment when reporting on a run.
 */
import { stat, readdir } from "node:fs/promises";
import { join } from "node:path";

import { Box, Text, useApp } from "ink";
import { useEffect, useState } from "react";

import { Layout } from "../../components/Layout.js";
import { archiveRoot } from "../../lib/corpus/paths.js";
import { readManifest, deriveStatus } from "../../lib/corpus/manifest.js";
import type { RunManifest } from "../../lib/corpus/manifest.js";

interface PhaseStat {
  phase: string;
  partialCount: number;
  logCount: number;
  graphCount: number;
  costUsd: number | null;
}

async function gatherPhaseStats(runDir: string, phases: readonly string[]): Promise<PhaseStat[]> {
  const result: PhaseStat[] = [];
  for (const phase of phases) {
    const partialsDir = join(runDir, "phases", phase, "partials");
    const logsDir = join(runDir, "phases", phase, "logs");
    const graphsDir = join(runDir, "phases", phase, "graphs");
    const costPath = join(runDir, "phases", phase, "cost.json");

    const partialCount = await safeCount(partialsDir);
    const logCount = await safeCount(logsDir);
    const graphCount = await safeCountGraphs(graphsDir);
    const costUsd = await safeReadCost(costPath);
    result.push({ phase, partialCount, logCount, graphCount, costUsd });
  }
  return result;
}

async function safeCount(dir: string): Promise<number> {
  try {
    const entries = await readdir(dir);
    return entries.length;
  } catch {
    return 0;
  }
}

async function safeCountGraphs(dir: string): Promise<number> {
  // graphs/ contains batch_w<W>b<B>_<ts>/<spec>/SG-*.mmd — recurse 2 levels.
  let count = 0;
  try {
    const batchDirs = await readdir(dir);
    for (const batch of batchDirs) {
      const batchPath = join(dir, batch);
      try {
        const specDirs = await readdir(batchPath);
        for (const spec of specDirs) {
          const specPath = join(batchPath, spec);
          try {
            const inner = await readdir(specPath);
            count += inner.filter((f) => f.endsWith(".mmd")).length;
          } catch {
            /* skip */
          }
        }
      } catch {
        /* skip */
      }
    }
  } catch {
    return 0;
  }
  return count;
}

async function safeReadCost(path: string): Promise<number | null> {
  try {
    const { readFile } = await import("node:fs/promises");
    const raw = await readFile(path, "utf8");
    const parsed = JSON.parse(raw) as { total_cost_usd?: number };
    return typeof parsed.total_cost_usd === "number" ? parsed.total_cost_usd : null;
  } catch {
    return null;
  }
}

interface CorpusShowCommandProps {
  runId: string;
  archiveRootOverride?: string;
}

function formatCost(usd: number | null): string {
  if (usd === null) return "—";
  if (usd === 0) return "$0.00";
  if (usd < 0.01) return "$<0.01";
  return `$${usd.toFixed(4)}`;
}

export function CorpusShowCommand({ runId, archiveRootOverride }: CorpusShowCommandProps) {
  const { exit } = useApp();
  const [manifest, setManifest] = useState<RunManifest | null>(null);
  const [phaseStats, setPhaseStats] = useState<PhaseStat[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resolvedRoot, setResolvedRoot] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    const root = archiveRoot(archiveRootOverride);
    setResolvedRoot(root);
    const runDir = join(root, runId);
    const manifestPath = join(runDir, "manifest.json");

    (async () => {
      try {
        await stat(manifestPath);
      } catch {
        if (cancelled) return;
        setError(`run-id not found under ${root}: ${runId}`);
        setTimeout(() => exit(new Error("corpus show: not found")), 30);
        return;
      }
      try {
        const m = await readManifest(manifestPath);
        const stats = await gatherPhaseStats(runDir, m.phases_completed ?? []);
        if (cancelled) return;
        setManifest(m);
        setPhaseStats(stats);
        setTimeout(() => exit(undefined), 30);
      } catch (err) {
        if (cancelled) return;
        setError((err as Error).message);
        setTimeout(() => exit(new Error("corpus show: read failed")), 30);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [runId, archiveRootOverride, exit]);

  if (error) {
    return (
      <Layout title={`speca corpus show ${runId}`} status={`error: ${error}`}>
        <Text color="red">{error}</Text>
      </Layout>
    );
  }

  if (manifest === null || phaseStats === null) {
    return (
      <Layout title={`speca corpus show ${runId}`} status="Loading manifest...">
        <Text dimColor>Reading {resolvedRoot}/{runId}/manifest.json...</Text>
      </Layout>
    );
  }

  const status = deriveStatus(manifest);
  const statusColor =
    status === "ok"
      ? "green"
      : status === "error"
        ? "red"
        : status === "pending"
          ? "yellow"
          : "gray";

  return (
    <Layout
      title={`speca corpus show ${runId}`}
      status={`status: ${status} · root: ${resolvedRoot}`}
    >
      <Box flexDirection="column">
        <Text>
          <Text bold>run_id      </Text>
          {manifest.run_id}
        </Text>
        <Text>
          <Text bold>status      </Text>
          <Text color={statusColor}>{status}</Text>
          {manifest.notes && manifest.notes !== "ok" ? (
            <Text dimColor>  ({manifest.notes})</Text>
          ) : null}
        </Text>
        <Text>
          <Text bold>started_at  </Text>
          {manifest.started_at}
        </Text>
        <Text>
          <Text bold>ended_at    </Text>
          {manifest.ended_at ?? "—"}
        </Text>
        <Text>
          <Text bold>speca_commit</Text>
          {"  "}
          {manifest.speca_commit || "—"}
        </Text>
        <Text>
          <Text bold>cost_total  </Text>
          {formatCost(manifest.cost_usd_total ?? 0)}
        </Text>
        <Text>
          <Text bold>spec_sources</Text>
          {manifest.spec_sources.length === 0 ? "  —" : ""}
        </Text>
        {manifest.spec_sources.map((url) => (
          <Text key={url} dimColor>
            {"  · "}
            {url}
          </Text>
        ))}
      </Box>

      <Box flexDirection="column" marginTop={1}>
        <Text bold underline>
          Phases
        </Text>
        <Box flexDirection="row" marginTop={1}>
          <Box width={8}><Text bold>phase</Text></Box>
          <Box width={12}><Text bold>partials</Text></Box>
          <Box width={10}><Text bold>logs</Text></Box>
          <Box width={10}><Text bold>graphs</Text></Box>
          <Box><Text bold>cost</Text></Box>
        </Box>
        {phaseStats.map((s) => (
          <Box key={s.phase} flexDirection="row">
            <Box width={8}><Text>{s.phase}</Text></Box>
            <Box width={12}><Text>{s.partialCount}</Text></Box>
            <Box width={10}><Text>{s.logCount}</Text></Box>
            <Box width={10}><Text>{s.graphCount}</Text></Box>
            <Box><Text>{formatCost(s.costUsd)}</Text></Box>
          </Box>
        ))}
      </Box>
    </Layout>
  );
}
