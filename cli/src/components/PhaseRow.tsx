import { Box, Text } from "ink";
import type { PhaseState } from "../lib/pipeline/store.js";
import { WorkerBadge } from "./WorkerBadge.js";

interface PhaseRowProps {
  phase: PhaseState;
  selected: boolean;
  /** Optional friendly name (e.g. "Spec Discovery"). */
  name?: string;
}

/**
 * Status → ASCII glyph mapping. Exported so tests can assert against the
 * source-of-truth glyph rather than pinning a literal string in two places.
 */
export const PHASE_STATUS_GLYPH: Record<PhaseState["status"], string> = {
  pending: "[ ]",
  running: "[>]",
  done: "[OK]",
  failed: "[X]",
};

const STATUS_GLYPH = PHASE_STATUS_GLYPH;

const STATUS_COLOR: Record<PhaseState["status"], string | undefined> = {
  pending: undefined,
  running: "cyan",
  done: "green",
  failed: "red",
};

export function PhaseRow({ phase, selected, name }: PhaseRowProps) {
  const glyph = STATUS_GLYPH[phase.status];
  const color = STATUS_COLOR[phase.status];
  const workers = Object.keys(phase.workerActivity).sort();
  const progress = (() => {
    if (phase.status === "done") {
      // `totalResults` is unset when the phase was reconstructed from disk
      // (speca attach) rather than observed via a phase-completed event —
      // show a plain "done" instead of a fabricated "0 results".
      if (phase.totalResults == null) return "done";
      return `${phase.totalResults} results`;
    }
    if (phase.status === "running") return `running (${phase.batchesObserved} events)`;
    if (phase.status === "failed") return `failed: ${phase.failureReason ?? "unknown"}`;
    return "pending";
  })();

  return (
    <Box>
      <Text color={selected ? "yellow" : undefined}>{selected ? "> " : "  "}</Text>
      <Box width={6}>
        <Text>{phase.id}</Text>
      </Box>
      <Box width={26}>
        <Text>{name ?? phase.id}</Text>
      </Box>
      <Box width={8}>
        <Text color={color}>{glyph}</Text>
      </Box>
      <Box flexGrow={1}>
        <Text>{progress}</Text>
      </Box>
      <Box>
        {workers.map((w, i) => (
          <Box key={w} marginLeft={i === 0 ? 0 : 1}>
            <WorkerBadge id={w} active={phase.status === "running"} />
          </Box>
        ))}
      </Box>
    </Box>
  );
}
