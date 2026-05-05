/**
 * Severity-coloured findings table for the finding browser (M4).
 */
import { Box, Text } from "ink";
import type { Finding } from "../lib/findings.js";

const SEVERITY_COLOR: Record<string, string> = {
  Critical: "red",
  High: "redBright",
  Medium: "yellow",
  Low: "cyan",
  Informational: "gray",
};

function severityColor(severity: string): string {
  return SEVERITY_COLOR[severity] ?? "white";
}

const VERDICT_COLOR: Record<string, string> = {
  Confirmed: "red",
  Disputed: "green",
  "Needs More Info": "yellow",
};

function verdictColor(verdict: string): string {
  return VERDICT_COLOR[verdict] ?? "white";
}

interface FindingTableProps {
  findings: Finding[];
  selectedIndex: number;
  pageSize?: number;
}

export function FindingTable({ findings, selectedIndex, pageSize = 15 }: FindingTableProps) {
  if (findings.length === 0) {
    return <Text dimColor>No findings to display.</Text>;
  }

  // Paginate around the selected index
  const pageStart = Math.max(0, Math.min(selectedIndex - Math.floor(pageSize / 2), findings.length - pageSize));
  const visible = findings.slice(Math.max(0, pageStart), Math.max(0, pageStart) + pageSize);
  const startIdx = Math.max(0, pageStart);

  return (
    <Box flexDirection="column">
      {/* Header */}
      <Box gap={1}>
        <Text bold>{" ".padEnd(2)}</Text>
        <Text bold>{"ID".padEnd(16)}</Text>
        <Text bold>{"Severity".padEnd(14)}</Text>
        <Text bold>{"Verdict".padEnd(16)}</Text>
        <Text bold>Summary</Text>
      </Box>
      <Text dimColor>{"─".repeat(80)}</Text>

      {visible.map((f, i) => {
        const idx = startIdx + i;
        const isSelected = idx === selectedIndex;
        const prefix = isSelected ? "> " : "  ";
        return (
          <Box key={f.propertyId + idx} gap={1}>
            <Text inverse={isSelected}>{prefix}</Text>
            <Text bold={isSelected}>{f.propertyId.padEnd(16).slice(0, 16)}</Text>
            <Text color={severityColor(f.severity)}>{(f.severity || "-").padEnd(14).slice(0, 14)}</Text>
            <Text color={verdictColor(f.verdict)}>{(f.verdict || "-").padEnd(16).slice(0, 16)}</Text>
            <Text wrap="truncate-end">{f.summary || f.classification || "-"}</Text>
          </Box>
        );
      })}

      <Text dimColor>
        {findings.length} findings | {selectedIndex + 1}/{findings.length} selected | [Enter] details [/] filter [q] back
      </Text>
    </Box>
  );
}
