import { Text } from "ink";

interface WorkerBadgeProps {
  id: string;
  active?: boolean;
}

/**
 * Compact worker indicator (e.g. `W0`). Active workers render bold; idle
 * workers are dimmed. Colour is paired with bold/dim weight so the dashboard
 * remains readable under NO_COLOR.
 */
export function WorkerBadge({ id, active = false }: WorkerBadgeProps) {
  if (active) {
    return (
      <Text bold color="green">
        {id}
      </Text>
    );
  }
  return <Text dimColor>{id}</Text>;
}
