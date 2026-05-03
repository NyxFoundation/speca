import { Box, Text } from "ink";

interface BudgetExceededModalProps {
  spent: number;
  cap: number | null;
  bumpUsd?: number;
}

/**
 * Read-only modal shown when the orchestrator emits `budget-exceeded`.
 *
 * In M3 we surface the hint and let the user re-run with a bigger
 * `--budget`. The interactive bump-and-resume path is M4+ work
 * (requires resume-capable orchestrator handshake).
 */
export function BudgetExceededModal({ spent, cap, bumpUsd }: BudgetExceededModalProps) {
  const bump = bumpUsd ?? Math.max(1, Math.ceil((cap ?? 1) * 0.5));
  return (
    <Box borderStyle="double" borderColor="red" paddingX={2} flexDirection="column">
      <Text bold color="red">
        Budget exceeded
      </Text>
      <Text>
        Spent <Text bold>${spent.toFixed(2)}</Text> of cap{" "}
        <Text bold>{cap == null ? "(unset)" : `$${cap.toFixed(2)}`}</Text>.
      </Text>
      <Text dimColor>
        Re-run with <Text bold>--budget ${(((cap ?? 0) || 0) + bump).toFixed(2)}</Text> to resume.
      </Text>
      <Text dimColor>(press q to quit)</Text>
    </Box>
  );
}
