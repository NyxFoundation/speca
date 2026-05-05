/**
 * Budget gauge — shows current spend vs. max budget as a progress bar.
 */
import { Box, Text } from "ink";

interface BudgetGaugeProps {
  costUsd: number;
  maxBudgetUsd: number;
}

export function BudgetGauge({ costUsd, maxBudgetUsd }: BudgetGaugeProps) {
  const ratio = maxBudgetUsd > 0 ? Math.min(costUsd / maxBudgetUsd, 1) : 0;
  const barWidth = 20;
  const filled = Math.round(ratio * barWidth);
  const empty = barWidth - filled;

  const color = ratio >= 0.9 ? "red" : ratio >= 0.7 ? "yellow" : "green";

  return (
    <Box gap={1}>
      <Text dimColor>Budget:</Text>
      <Text color={color}>
        [{"#".repeat(filled)}{".".repeat(empty)}]
      </Text>
      <Text color={color}>
        ${costUsd.toFixed(2)} / ${maxBudgetUsd.toFixed(2)}
      </Text>
      <Text dimColor>({(ratio * 100).toFixed(0)}%)</Text>
    </Box>
  );
}
