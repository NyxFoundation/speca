import { Box, Text } from "ink";
import { highlight, supportsLanguage } from "cli-highlight";

export type MessageRole = "user" | "assistant" | "system";

export interface MessageBubbleProps {
  role: MessageRole;
  /** Display label override (e.g. account email). */
  speaker?: string;
  text: string;
  /** When true, renders a trailing cursor "_" (used for in-flight assistant text). */
  streaming?: boolean;
}

const ROLE_COLOR: Record<MessageRole, "green" | "magenta" | "yellow"> = {
  user: "green",
  assistant: "magenta",
  system: "yellow",
};

function defaultSpeaker(role: MessageRole): string {
  switch (role) {
    case "user":
      return "You";
    case "assistant":
      return "Claude";
    case "system":
      return "system";
  }
}

interface Block {
  kind: "text" | "code";
  language?: string;
  text: string;
}

/**
 * Split a message body into text + fenced-code blocks. Tolerant: an unclosed
 * fence is treated as a code block running to the end of the message (matches
 * how ChatGPT-style chat UIs render mid-stream snippets).
 */
export function splitBlocks(input: string): Block[] {
  const blocks: Block[] = [];
  const lines = input.split(/\r?\n/);
  let i = 0;
  let textBuf: string[] = [];
  const flushText = () => {
    if (textBuf.length > 0) {
      blocks.push({ kind: "text", text: textBuf.join("\n") });
      textBuf = [];
    }
  };
  while (i < lines.length) {
    const line = lines[i] ?? "";
    const fence = /^```(\S*)\s*$/.exec(line);
    if (fence) {
      flushText();
      const lang = fence[1] ?? "";
      const codeLines: string[] = [];
      i++;
      while (i < lines.length) {
        const inner = lines[i] ?? "";
        if (/^```\s*$/.test(inner)) {
          i++;
          break;
        }
        codeLines.push(inner);
        i++;
      }
      blocks.push({ kind: "code", language: lang, text: codeLines.join("\n") });
      continue;
    }
    textBuf.push(line);
    i++;
  }
  flushText();
  return blocks;
}

function renderCode(text: string, language?: string): string {
  if (!language || !supportsLanguage(language)) {
    try {
      // Auto-detect when language is missing — cli-highlight handles unknown
      // languages by falling back to raw text without throwing.
      return highlight(text, { ignoreIllegals: true });
    } catch {
      return text;
    }
  }
  try {
    return highlight(text, { language, ignoreIllegals: true });
  } catch {
    return text;
  }
}

export function MessageBubble({ role, speaker, text, streaming = false }: MessageBubbleProps) {
  const label = speaker ?? defaultSpeaker(role);
  const color = ROLE_COLOR[role];
  const blocks = splitBlocks(text);
  const display = streaming ? `${text}_` : text;
  const blocksToRender = streaming ? splitBlocks(display) : blocks;

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text color={color} bold>
        {label}:
      </Text>
      <Box flexDirection="column" paddingLeft={2}>
        {blocksToRender.map((b, idx) => {
          if (b.kind === "code") {
            return (
              <Box key={`b-${idx}`} flexDirection="column" marginY={0}>
                <Text dimColor>{b.language ? `\`\`\`${b.language}` : "```"}</Text>
                <Text>{renderCode(b.text, b.language)}</Text>
                <Text dimColor>```</Text>
              </Box>
            );
          }
          return (
            <Text key={`b-${idx}`} wrap="wrap">
              {b.text || " "}
            </Text>
          );
        })}
      </Box>
    </Box>
  );
}
