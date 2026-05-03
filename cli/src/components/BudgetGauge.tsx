import { Box, Text } from "ink";

interface BudgetGaugeProps {
  totalUsd: number;
  maxBudgetUsd: number | null;
}

/**
 * Renders `$X.XX / $Y.YY`, turning yellow at 80% and red at 100% (per
 * SPEC §5.3.3). When the cap is unknown, only the spent amount is shown.
 */
export function BudgetGauge({ totalUsd, maxBudgetUsd }: BudgetGaugeProps) {
  const spent = `$${totalUsd.toFixed(2)}`;
  if (maxBudgetUsd == null) {
    return (
      <Box>
        <Text>budget: {spent}</Text>
      </Box>
    );
  }
  const ratio = maxBudgetUsd > 0 ? totalUsd / maxBudgetUsd : 0;
  const color = ratio >= 1 ? "red" : ratio >= 0.8 ? "yellow" : undefined;
  return (
    <Box>
      <Text>budget: </Text>
      <Text color={color}>
        {spent} / ${maxBudgetUsd.toFixed(2)}
      </Text>
    </Box>
  );
}
