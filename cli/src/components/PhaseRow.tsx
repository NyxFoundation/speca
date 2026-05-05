/**
 * A single phase row in the pipeline dashboard.
 * Shows phase ID, status indicator, duration, and result count.
 */
import { Box, Text } from "ink";

export type PhaseStatus = "pending" | "running" | "completed" | "failed" | "budget-exceeded" | "circuit-breaker";

export interface PhaseRowData {
  phase: string;
  status: PhaseStatus;
  durationS?: number;
  totalResults?: number;
  reason?: string;
  model?: string;
}

const STATUS_ICON: Record<PhaseStatus, { text: string; color: string }> = {
  pending: { text: "-", color: "gray" },
  running: { text: "*", color: "yellow" },
  completed: { text: "v", color: "green" },
  failed: { text: "x", color: "red" },
  "budget-exceeded": { text: "$", color: "red" },
  "circuit-breaker": { text: "!", color: "red" },
};

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m${s}s`;
}

export function PhaseRow({ data }: { data: PhaseRowData }) {
  const icon = STATUS_ICON[data.status];
  return (
    <Box gap={1}>
      <Text color={icon.color}>[{icon.text}]</Text>
      <Text bold>{data.phase.padEnd(4)}</Text>
      <Text color={icon.color}>
        {data.status === "running" ? "running..." : data.status}
      </Text>
      {data.durationS !== undefined && (
        <Text dimColor>({formatDuration(data.durationS)})</Text>
      )}
      {data.totalResults !== undefined && (
        <Text color="cyan">{data.totalResults} results</Text>
      )}
      {data.reason && (
        <Text color="red">{data.reason}</Text>
      )}
      {data.model && data.status === "running" && (
        <Text dimColor>[{data.model}]</Text>
      )}
    </Box>
  );
}
