import { Box, Text } from "ink";

interface StatusBarProps {
  showLogs: boolean;
  lastError?: string;
}

const KEYS: Array<{ key: string; label: string }> = [
  { key: "Enter", label: "detail" },
  { key: "s", label: "stop" },
  { key: "f", label: "force" },
  { key: "l", label: "toggle log" },
  { key: "↑/↓", label: "select" },
  { key: "q", label: "quit" },
];

export function StatusBar({ showLogs, lastError }: StatusBarProps) {
  return (
    <Box flexDirection="column" paddingX={1}>
      <Box>
        {KEYS.map((k, i) => (
          <Box key={k.key} marginRight={2}>
            <Text>
              [<Text bold>{k.key}</Text>] {k.label}
              {k.key === "l" ? ` (${showLogs ? "on" : "off"})` : ""}
            </Text>
          </Box>
        ))}
      </Box>
      {lastError ? (
        <Box>
          <Text color="red">{lastError}</Text>
        </Box>
      ) : null}
    </Box>
  );
}
