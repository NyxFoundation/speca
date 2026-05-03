/**
 * CodePeek — render a syntax-highlighted code window for the selected
 * finding. ANSI escapes from `cli-highlight` flow straight through Ink's
 * `<Text>` because Ink preserves embedded escapes.
 */
import { Box, Text } from "ink";

import type { CodePeekResult } from "../lib/findings/codePeek.js";
import { highlightCode } from "../lib/findings/highlight.js";

interface CodePeekProps {
  peek: CodePeekResult | null;
  loading: boolean;
  /** Used by tests to disable color escapes. */
  plain?: boolean;
}

export function CodePeek({ peek, loading, plain }: CodePeekProps) {
  if (loading) {
    return <Text dimColor>(loading code…)</Text>;
  }
  if (!peek) {
    return <Text dimColor>(press [c] to open code peek)</Text>;
  }
  if (!peek.ok) {
    return (
      <Box flexDirection="column">
        <Text color="yellow">{`code peek failed: ${peek.message}`}</Text>
        {peek.filePath ? <Text dimColor>{peek.filePath}</Text> : null}
      </Box>
    );
  }
  const joined = peek.lines.join("\n");
  const highlighted = highlightCode(joined, { language: peek.language, plain });
  const out = highlighted.split("\n");
  const gutterWidth = String(peek.endLine).length;
  return (
    <Box flexDirection="column">
      <Text dimColor>{`${peek.filePath}  (lines ${peek.startLine}-${peek.endLine}, ${peek.language})`}</Text>
      {out.map((line, idx) => {
        const lineNo = peek.startLine + idx;
        return (
          <Box key={idx}>
            <Text dimColor>{padLeft(String(lineNo), gutterWidth)}: </Text>
            <Text>{line}</Text>
          </Box>
        );
      })}
    </Box>
  );
}

function padLeft(s: string, n: number): string {
  if (s.length >= n) return s;
  return " ".repeat(n - s.length) + s;
}
