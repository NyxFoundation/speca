import { Box, Text } from "ink";
import { BudgetGauge } from "./BudgetGauge.js";

interface HeaderProps {
  cwd: string;
  pipelineStatus: string;
  totalUsd: number;
  maxBudgetUsd: number | null;
}

export function Header({ cwd, pipelineStatus, totalUsd, maxBudgetUsd }: HeaderProps) {
  return (
    <Box borderStyle="round" paddingX={1} flexDirection="row" justifyContent="space-between">
      <Box>
        <Text bold>speca run</Text>
        <Text>  </Text>
        <Text dimColor>project: {cwd}</Text>
        <Text>  </Text>
        <Text>
          status: <Text bold>{pipelineStatus}</Text>
        </Text>
      </Box>
      <BudgetGauge totalUsd={totalUsd} maxBudgetUsd={maxBudgetUsd} />
    </Box>
  );
}
