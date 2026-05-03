import { Box, Text, useApp, useInput } from "ink";
import { useEffect, useMemo, useState } from "react";

import type { PipelineRunHandleTyped } from "../lib/pipeline/spawn.js";
import type { PipelineSnapshot, PipelineStore } from "../lib/pipeline/store.js";
import { phaseName } from "../lib/pipeline/phase-names.js";
import { usePipelineStore } from "../lib/pipeline/useStore.js";
import { BudgetExceededModal } from "./BudgetExceededModal.js";
import { Header } from "./Header.js";
import { LogPane } from "./LogPane.js";
import { PhaseRow } from "./PhaseRow.js";
import { StatusBar } from "./StatusBar.js";

export interface DashboardProps {
  store: PipelineStore;
  /** Optional: when provided, key bindings that affect the run (s/f) act on it. */
  handle?: PipelineRunHandleTyped;
  /** cwd label rendered in the header. */
  cwd: string;
  /** Resolves the dashboard once the run completes (used by run.tsx). */
  onExit?: () => void;
}

export function Dashboard({ store, handle, cwd, onExit }: DashboardProps) {
  const snapshot = usePipelineStore(store);
  const { exit } = useApp();
  const [showLogs, setShowLogs] = useState(true);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [showDetail, setShowDetail] = useState(false);

  const orderedPhases = useMemo(
    () => snapshot.phaseOrder.map((id) => snapshot.phases.get(id)).filter((p): p is NonNullable<typeof p> => Boolean(p)),
    [snapshot.phaseOrder, snapshot.phases],
  );

  // Keep selection in bounds when phase list changes.
  useEffect(() => {
    if (orderedPhases.length === 0 && selectedIdx !== 0) {
      setSelectedIdx(0);
    } else if (selectedIdx >= orderedPhases.length && orderedPhases.length > 0) {
      setSelectedIdx(orderedPhases.length - 1);
    }
  }, [orderedPhases.length, selectedIdx]);

  // Auto-exit shortly after the pipeline reaches a terminal state so the
  // dashboard does not hang in the foreground after a one-shot run.
  useEffect(() => {
    const terminal = ["completed", "failed", "budget-exceeded", "circuit-broken"].includes(snapshot.pipelineStatus);
    if (!terminal) return;
    const timer = setTimeout(() => {
      onExit?.();
      exit();
    }, 250);
    return () => clearTimeout(timer);
  }, [snapshot.pipelineStatus, onExit, exit]);

  useInput((input, key) => {
    if (input === "q") {
      handle?.kill?.();
      onExit?.();
      exit();
      return;
    }
    if (input === "s") {
      handle?.stop?.();
      return;
    }
    if (input === "f") {
      handle?.kill?.();
      return;
    }
    if (input === "l") {
      setShowLogs((v) => !v);
      return;
    }
    if (key.upArrow) {
      setSelectedIdx((i) => Math.max(0, i - 1));
      return;
    }
    if (key.downArrow) {
      setSelectedIdx((i) => Math.min(Math.max(0, orderedPhases.length - 1), i + 1));
      return;
    }
    if (key.return) {
      setShowDetail((v) => !v);
    }
  });

  const selected = orderedPhases[selectedIdx];

  return (
    <Box flexDirection="column">
      <Header
        cwd={cwd}
        pipelineStatus={snapshot.pipelineStatus}
        totalUsd={snapshot.cost.total_usd}
        maxBudgetUsd={snapshot.cost.max_budget_usd}
      />

      {snapshot.pipelineStatus === "budget-exceeded" ? (
        <BudgetExceededModal
          spent={snapshot.cost.total_usd}
          cap={snapshot.cost.max_budget_usd}
        />
      ) : null}

      <Box borderStyle="round" flexDirection="column" paddingX={1}>
        <Box>
          <Box width={8}>
            <Text bold>  Phase</Text>
          </Box>
          <Box width={26}>
            <Text bold>Name</Text>
          </Box>
          <Box width={8}>
            <Text bold>Status</Text>
          </Box>
          <Box flexGrow={1}>
            <Text bold>Progress</Text>
          </Box>
          <Box>
            <Text bold>Workers</Text>
          </Box>
        </Box>
        {orderedPhases.length === 0 ? (
          <Text dimColor>(no phases registered yet)</Text>
        ) : (
          orderedPhases.map((phase, i) => (
            <PhaseRow key={phase.id} phase={phase} selected={i === selectedIdx} name={phaseName(phase.id)} />
          ))
        )}
      </Box>

      {showDetail && selected ? <PhaseDetail snapshot={snapshot} phaseId={selected.id} /> : null}
      {showLogs ? <LogPane logs={snapshot.logs} maxRows={10} /> : null}

      <StatusBar showLogs={showLogs} lastError={snapshot.lastError} />
    </Box>
  );
}

interface PhaseDetailProps {
  snapshot: PipelineSnapshot;
  phaseId: string;
}

function PhaseDetail({ snapshot, phaseId }: PhaseDetailProps) {
  const phase = snapshot.phases.get(phaseId);
  if (!phase) return null;
  const workerEntries = Object.entries(phase.workerActivity);
  return (
    <Box borderStyle="round" flexDirection="column" paddingX={1}>
      <Text bold>Detail: {phase.id} {phaseName(phase.id)}</Text>
      <Text>status: {phase.status}</Text>
      {phase.workers != null ? <Text>workers: {phase.workers} (max concurrent {phase.maxConcurrent ?? "?"})</Text> : null}
      {phase.model ? <Text>model: {phase.model}</Text> : null}
      {phase.startedAt ? <Text>started: {phase.startedAt}</Text> : null}
      {phase.endedAt ? <Text>ended:   {phase.endedAt}</Text> : null}
      {phase.durationS != null ? <Text>duration: {phase.durationS.toFixed(2)}s</Text> : null}
      {phase.totalResults != null ? <Text>results: {phase.totalResults}</Text> : null}
      {phase.failureReason ? <Text color="red">reason: {phase.failureReason}</Text> : null}
      {workerEntries.length > 0 ? (
        <Box flexDirection="column" marginTop={1}>
          <Text dimColor>recent worker activity:</Text>
          {workerEntries.map(([w, summary]) => (
            <Text key={w}>
              {w}: {summary}
            </Text>
          ))}
        </Box>
      ) : null}
    </Box>
  );
}
