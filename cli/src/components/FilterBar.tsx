/**
 * FilterBar — show the current filter / search state and, when in edit mode,
 * accept input.  Ink does not ship a TextInput widget, so we maintain the
 * buffer in the parent and render the cursor manually.
 */
import { Box, Text } from "ink";

interface FilterBarProps {
  /** The active applied filter. */
  applied: string;
  /** When true, show editor with the buffer contents. */
  editing: boolean;
  buffer: string;
  /** When set, render after the buffer as a user-visible error. */
  error?: string | null;
  /** Sort mode (rendered as a hint on the right). */
  sortMode: string;
  /** Total/match counters. */
  total: number;
  matched: number;
  /** Mode label e.g. 'filter' or '/' for text-search shortcut. */
  modeLabel?: string;
}

export function FilterBar({
  applied,
  editing,
  buffer,
  error,
  sortMode,
  total,
  matched,
  modeLabel = "filter",
}: FilterBarProps) {
  return (
    <Box flexDirection="column">
      <Box>
        <Text dimColor>{`${matched} / ${total} findings   sort: ${sortMode}`}</Text>
      </Box>
      {editing ? (
        <Box>
          <Text color="green">{`${modeLabel}> `}</Text>
          <Text>{buffer}</Text>
          <Text color="green">_</Text>
        </Box>
      ) : (
        <Box>
          <Text dimColor>filter: </Text>
          <Text>{applied || "(none)"}</Text>
        </Box>
      )}
      {error ? (
        <Box>
          <Text color="red">{`! ${error}`}</Text>
        </Box>
      ) : null}
    </Box>
  );
}
