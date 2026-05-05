/**
 * `speca run` — launch the pipeline and display a live dashboard.
 *
 * Spawns `uv run python3 scripts/run_phase.py --json` and streams
 * typed events into an Ink TUI with phase rows, log pane, and budget gauge.
 *
 * Spec ref: Issue #3 M3, SPECA_CLI_SPEC §9.
 */
import { Box, Text, useApp, useInput } from "ink";
import { useCallback, useEffect, useRef, useState } from "react";
import { BudgetGauge } from "../components/BudgetGauge.js";
import { Layout } from "../components/Layout.js";
import { LogPane } from "../components/LogPane.js";
import { PhaseRow, type PhaseRowData, type PhaseStatus } from "../components/PhaseRow.js";
import type { PipelineEvent } from "../lib/events.js";
import { spawnPipeline, type ProcessBridge } from "../lib/process-bridge.js";

export interface RunCommandProps {
  phases?: string[];
  target?: string;
  workers?: number;
  maxConcurrent?: number;
  force?: boolean;
  cwd?: string;
}

interface DashboardState {
  phases: Map<string, PhaseRowData>;
  logs: string[];
  budget: { costUsd: number; maxBudgetUsd: number } | null;
  pipelineStatus: "starting" | "running" | "completed" | "failed";
  exitCode: number | null;
  durationS: number | null;
}

function buildInitialState(): DashboardState {
  return {
    phases: new Map(),
    logs: [],
    budget: null,
    pipelineStatus: "starting",
    exitCode: null,
    durationS: null,
  };
}

export function RunCommand(props: RunCommandProps) {
  const { exit } = useApp();
  const [state, setState] = useState<DashboardState>(buildInitialState);
  const bridgeRef = useRef<ProcessBridge | null>(null);

  const handleEvent = useCallback((event: PipelineEvent) => {
    setState((prev) => {
      const next = { ...prev, phases: new Map(prev.phases) };
      switch (event.type) {
        case "pipeline-started":
          next.pipelineStatus = "running";
          for (const p of event.phases) {
            if (!next.phases.has(p)) {
              next.phases.set(p, { phase: p, status: "pending" });
            }
          }
          break;

        case "phase-started":
          next.phases.set(event.phase, {
            phase: event.phase,
            status: "running",
            model: event.model,
          });
          break;

        case "phase-completed":
          next.phases.set(event.phase, {
            phase: event.phase,
            status: "completed",
            durationS: event.duration_s,
            totalResults: event.total_results,
          });
          break;

        case "phase-failed":
          next.phases.set(event.phase, {
            phase: event.phase,
            status: "failed",
            durationS: event.duration_s,
            reason: event.reason,
          });
          break;

        case "budget-exceeded":
          next.phases.set(event.phase, {
            ...(next.phases.get(event.phase) ?? { phase: event.phase, status: "budget-exceeded" }),
            status: "budget-exceeded",
            durationS: event.duration_s,
          });
          next.budget = { costUsd: event.cost_usd, maxBudgetUsd: event.max_budget_usd };
          break;

        case "circuit-breaker-tripped":
          next.phases.set(event.phase, {
            phase: event.phase,
            status: "circuit-breaker",
            durationS: event.duration_s,
            reason: event.reason,
          });
          break;

        case "pipeline-completed":
          next.pipelineStatus = "completed";
          next.durationS = event.duration_s;
          break;
      }
      return next;
    });
  }, []);

  const handleStderr = useCallback((line: string) => {
    setState((prev) => ({
      ...prev,
      logs: [...prev.logs, line],
    }));
  }, []);

  useEffect(() => {
    const bridge = spawnPipeline({
      phases: props.phases,
      target: props.target,
      workers: props.workers,
      maxConcurrent: props.maxConcurrent,
      force: props.force,
      cwd: props.cwd,
    });
    bridgeRef.current = bridge;

    bridge.events.on("event", handleEvent);
    bridge.events.on("stderr", handleStderr);
    bridge.events.on("error", (err: Error) => {
      setState((prev) => ({
        ...prev,
        pipelineStatus: "failed",
        logs: [...prev.logs, `[ERROR] ${err.message}`],
      }));
    });

    bridge.exitPromise.then((code) => {
      setState((prev) => ({
        ...prev,
        exitCode: code,
        pipelineStatus: code === 0 ? "completed" : "failed",
      }));
    });

    return () => {
      bridge.events.removeAllListeners();
    };
  }, [props, handleEvent, handleStderr]);

  // Key bindings
  useInput((input, key) => {
    if (input === "q" || (key.ctrl && input === "c")) {
      bridgeRef.current?.stop();
      exit();
    }
  });

  const phaseRows = Array.from(state.phases.values());
  const statusText =
    state.pipelineStatus === "completed"
      ? `Done${state.durationS ? ` in ${state.durationS.toFixed(0)}s` : ""} (exit ${state.exitCode})`
      : state.pipelineStatus === "failed"
        ? `Failed (exit ${state.exitCode ?? "?"})`
        : state.pipelineStatus === "running"
          ? "Running... (q to quit)"
          : "Starting...";

  return (
    <Layout title="SPECA Pipeline" status={statusText}>
      <Box flexDirection="column" gap={0}>
        {phaseRows.length === 0 ? (
          <Text dimColor>Waiting for pipeline events...</Text>
        ) : (
          phaseRows.map((row) => <PhaseRow key={row.phase} data={row} />)
        )}
      </Box>

      {state.budget && (
        <Box marginTop={1}>
          <BudgetGauge costUsd={state.budget.costUsd} maxBudgetUsd={state.budget.maxBudgetUsd} />
        </Box>
      )}

      <Box marginTop={1}>
        <LogPane lines={state.logs} />
      </Box>
    </Layout>
  );
}
