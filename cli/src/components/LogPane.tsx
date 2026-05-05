/**
 * Scrollable log pane that shows the last N stderr lines from the pipeline.
 */
import { Box, Text } from "ink";

interface LogPaneProps {
  lines: string[];
  maxLines?: number;
}

export function LogPane({ lines, maxLines = 12 }: LogPaneProps) {
  const visible = lines.slice(-maxLines);
  return (
    <Box flexDirection="column" borderStyle="single" borderColor="gray" paddingX={1}>
      <Text bold dimColor>
        Logs ({lines.length} lines)
      </Text>
      {visible.length === 0 ? (
        <Text dimColor>Waiting for output...</Text>
      ) : (
        visible.map((line, i) => (
          <Text key={i} wrap="truncate-end">
            {line}
          </Text>
        ))
      )}
    </Box>
  );
}
