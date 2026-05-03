import { Box, Text } from "ink";
import type { LogLine } from "../lib/pipeline/log-watcher.js";

interface LogPaneProps {
  logs: LogLine[];
  maxRows?: number;
}

const SEVERITY_COLOR: Record<LogLine["severity"], string | undefined> = {
  info: undefined,
  warn: "yellow",
  error: "red",
};

/**
 * Bottom log pane. Shows the most recent `maxRows` lines from the ring
 * buffer. Auto-tails (always shows the tail; no scroll keys in M3).
 */
export function LogPane({ logs, maxRows = 10 }: LogPaneProps) {
  const tail = logs.slice(-maxRows);
  return (
    <Box borderStyle="round" flexDirection="column" paddingX={1}>
      <Box>
        <Text bold>Live log</Text>
        <Text dimColor> ({logs.length} events, showing tail {tail.length})</Text>
      </Box>
      {tail.length === 0 ? (
        <Text dimColor>(no log lines yet)</Text>
      ) : (
        tail.map((line, i) => {
          const prefix = `[${line.phase || "--"}/W${line.worker || "?"}/B${line.batch || "?"}]`;
          return (
            <Text key={`${line.sourcePath}:${i}:${line.ts}`} color={SEVERITY_COLOR[line.severity]}>
              {prefix} {line.summary}
            </Text>
          );
        })
      )}
    </Box>
  );
}
