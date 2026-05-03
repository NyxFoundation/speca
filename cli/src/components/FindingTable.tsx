/**
 * FindingTable — render a windowed list of findings, severity-coloured.
 *
 * The table is intentionally simple (no horizontal scroll, no column resize):
 * we keep the columns short and let `summary` truncate. Selection is driven
 * by the parent via `selectedIndex`, and we slice into a viewport so very
 * long lists do not flood the terminal.
 */
import { Box, Text } from "ink";

import type { Finding, Severity } from "../lib/findings/types.js";

interface FindingTableProps {
  findings: Finding[];
  selectedIndex: number;
  viewportHeight?: number;
}

const SEVERITY_COLORS: Record<Severity | "", string> = {
  Critical: "red",
  High: "redBright",
  Medium: "yellow",
  Low: "green",
  Informational: "gray",
  "": "gray",
};

const SEVERITY_LABEL: Record<Severity | "", string> = {
  Critical: "CRIT",
  High: "HIGH",
  Medium: "MED ",
  Low: "LOW ",
  Informational: "INFO",
  "": "----",
};

function shortenVerdict(v: string): string {
  if (!v) return "—";
  // CONFIRMED_VULNERABILITY -> CONFIRMED_VULN, etc, to fit the column.
  return v.replace("VULNERABILITY", "VULN").replace("POTENTIAL", "POTENTIAL").slice(0, 20);
}

function shortenLocation(f: Finding): string {
  const loc = f.primaryLocation;
  if (!loc || !loc.file) return "—";
  const parts = loc.file.split(/[\\/]/);
  const name = parts[parts.length - 1];
  if (loc.startLine > 0) return `${name}:${loc.startLine}`;
  return name;
}

function clampViewport(total: number, selected: number, height: number): { start: number; end: number } {
  if (total <= height) return { start: 0, end: total };
  const half = Math.floor(height / 2);
  let start = Math.max(0, selected - half);
  let end = start + height;
  if (end > total) {
    end = total;
    start = end - height;
  }
  return { start, end };
}

export function FindingTable({ findings, selectedIndex, viewportHeight = 12 }: FindingTableProps) {
  if (findings.length === 0) {
    return (
      <Box>
        <Text dimColor>(no findings match the current filter)</Text>
      </Box>
    );
  }
  const { start, end } = clampViewport(findings.length, selectedIndex, viewportHeight);
  const rows = findings.slice(start, end);
  return (
    <Box flexDirection="column">
      <Box>
        <Text dimColor>  # </Text>
        <Text dimColor>SEV  </Text>
        <Text dimColor>VERDICT              </Text>
        <Text dimColor>PROPERTY                                  </Text>
        <Text dimColor>LOCATION</Text>
      </Box>
      {rows.map((f, i) => {
        const absoluteIdx = start + i;
        const selected = absoluteIdx === selectedIndex;
        const sev = (f.severity || "") as Severity | "";
        const sevColor = SEVERITY_COLORS[sev];
        const sevLabel = SEVERITY_LABEL[sev];
        const arrow = selected ? "▶ " : "  ";
        const propText = padRight(f.propertyId, 40);
        const verdictText = padRight(shortenVerdict(f.verdict), 20);
        const summary = f.summary ? f.summary.split(/\r?\n/)[0] : "";
        const numStr = padLeft(String(absoluteIdx + 1), 3);
        const summarySuffix = summary ? `  ${ellipsis(summary, 60)}` : "";
        return (
          <Box key={`row-${absoluteIdx}-${f.id}`}>
            <Text color={selected ? "cyan" : undefined}>{arrow}</Text>
            <Text dimColor>{`${numStr} `}</Text>
            <Text color={sevColor} bold>
              {sevLabel}
            </Text>
            <Text>{` `}</Text>
            <Text color="cyan">{`${verdictText} `}</Text>
            <Text>{`${propText} `}</Text>
            <Text dimColor>{`${shortenLocation(f)}${summarySuffix}`}</Text>
          </Box>
        );
      })}
      {findings.length > rows.length ? (
        <Box>
          <Text dimColor>{`  … showing ${start + 1}-${end} of ${findings.length}`}</Text>
        </Box>
      ) : null}
    </Box>
  );
}

function padRight(s: string, n: number): string {
  if (s.length >= n) return `${s.slice(0, n - 1)}…`;
  return s + " ".repeat(n - s.length);
}

function padLeft(s: string, n: number): string {
  if (s.length >= n) return s;
  return " ".repeat(n - s.length) + s;
}

function ellipsis(s: string, n: number): string {
  if (s.length <= n) return s;
  return `${s.slice(0, n - 1)}…`;
}
