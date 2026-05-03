import { Text } from "ink";
import { useEffect, useState } from "react";

const FRAMES = ["|", "/", "-", "\\"]; // ASCII spinner — works on Windows console

interface Props {
  label?: string;
  intervalMs?: number;
}

/**
 * Tiny ASCII-only spinner used while the assistant is generating. Avoids
 * `ink-spinner` (extra dep, less control) and uses ASCII because the spec
 * forbids emoji and the project targets Windows consoles where unicode
 * spinners can render as boxes.
 */
export function StreamingIndicator({ label = "Claude is thinking", intervalMs = 120 }: Props) {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % FRAMES.length), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return (
    <Text color="cyan">
      {FRAMES[i]} {label}...
    </Text>
  );
}
