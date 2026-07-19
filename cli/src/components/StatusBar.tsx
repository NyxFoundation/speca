import { Box, Text } from "ink";

interface StatusBarProps {
  showLogs: boolean;
  lastError?: string;
  /** Read-only mode (speca attach): hide the stop / force bindings. */
  readOnly?: boolean;
}

const KEYS: Array<{ key: string; label: string }> = [
  { key: "Enter", label: "detail" },
  { key: "s", label: "stop" },
  { key: "f", label: "force" },
  { key: "l", label: "toggle log" },
  { key: "↑/↓", label: "select" },
  { key: "q", label: "quit" },
];

/** Bindings shown in read-only mode — no run-mutating actions. */
const READ_ONLY_KEYS: Array<{ key: string; label: string }> = KEYS.filter(
  (k) => k.key !== "s" && k.key !== "f",
);

export function StatusBar({ showLogs, lastError, readOnly = false }: StatusBarProps) {
  const keys = readOnly ? READ_ONLY_KEYS : KEYS;
  return (
    <Box flexDirection="column" paddingX={1}>
      <Box>
        {readOnly ? (
          <Box marginRight={2}>
            <Text dimColor>read-only</Text>
          </Box>
        ) : null}
        {keys.map((k, i) => (
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
