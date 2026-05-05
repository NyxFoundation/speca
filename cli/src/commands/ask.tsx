/**
 * `speca ask` / Ask Claude pane (M5).
 *
 * Interactive chat preloaded with a selected finding as context.
 * Each turn spawns `claude -p <prompt> --output-format stream-json --resume <session-id>`.
 *
 * Spec ref: Issue #3 M5, SPECA_CLI_SPEC §8.5.
 */
import { Box, Text, useApp, useInput } from "ink";
import { useCallback, useEffect, useRef, useState } from "react";
import { Layout } from "../components/Layout.js";
import {
  askClaude,
  buildFindingContext,
  loadSession,
  saveSession,
  type ChatMessage,
} from "../lib/claude-bridge.js";
import type { Finding } from "../lib/findings.js";

export interface AskCommandProps {
  /** Pre-selected finding to load as context */
  finding?: Finding;
  /** Project directory (for session persistence) */
  cwd?: string;
}

export function AskCommand(props: AskCommandProps) {
  const { exit } = useApp();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [currentStream, setCurrentStream] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);
  const cwd = props.cwd ?? process.cwd();
  const initialized = useRef(false);

  // Load session on mount
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    loadSession(cwd).then((info) => {
      if (info.sessionId) setSessionId(info.sessionId);
    });
  }, [cwd]);

  const sendMessage = useCallback(
    (userPrompt: string) => {
      if (!userPrompt.trim() || streaming) return;

      // Build prompt with finding context on first message
      let fullPrompt = userPrompt;
      if (messages.length === 0 && props.finding) {
        const context = buildFindingContext(props.finding);
        fullPrompt = `${context}\n\n---\n\nUser question: ${userPrompt}`;
      }

      setMessages((prev) => [...prev, { role: "user", content: userPrompt }]);
      setInputText("");
      setStreaming(true);
      setCurrentStream("");

      const bridge = askClaude(fullPrompt, sessionId, cwd);

      bridge.events.on("token", (token: string) => {
        setCurrentStream((prev) => prev + token);
      });

      bridge.events.on("session", (id: string) => {
        setSessionId(id);
        saveSession({ sessionId: id, projectDir: cwd });
      });

      bridge.events.on("error", (err: Error) => {
        setError(err.message);
        setStreaming(false);
      });

      bridge.events.on("done", (fullText: string) => {
        const response = fullText || currentStream;
        setMessages((prev) => [...prev, { role: "assistant", content: response }]);
        setCurrentStream("");
        setStreaming(false);
      });
    },
    [streaming, messages, props.finding, sessionId, cwd, currentStream],
  );

  useInput((input, key) => {
    if (key.ctrl && input === "c") {
      exit();
      return;
    }
    if (input === "q" && !inputText && !streaming) {
      exit();
      return;
    }

    if (streaming) return; // ignore input while streaming

    if (key.return) {
      sendMessage(inputText);
    } else if (key.backspace || key.delete) {
      setInputText((prev) => prev.slice(0, -1));
    } else if (input && !key.ctrl && !key.meta) {
      setInputText((prev) => prev + input);
    }
  });

  const statusText = sessionId
    ? `Session: ${sessionId.slice(0, 12)}... | ${messages.length} messages`
    : "New session";

  return (
    <Layout title="Ask Claude" status={statusText}>
      <Box flexDirection="column">
        {/* Finding context banner */}
        {props.finding && messages.length === 0 && (
          <Box marginBottom={1} borderStyle="round" borderColor="cyan" paddingX={1}>
            <Text>
              Context: <Text bold>{props.finding.propertyId}</Text> — {props.finding.summary || props.finding.classification}
            </Text>
          </Box>
        )}

        {/* Chat history */}
        {messages.map((msg, i) => (
          <Box key={i} marginBottom={1} flexDirection="column">
            <Text bold color={msg.role === "user" ? "blue" : "green"}>
              {msg.role === "user" ? "You" : "Claude"}:
            </Text>
            <Text wrap="wrap">{msg.content}</Text>
          </Box>
        ))}

        {/* Streaming response */}
        {streaming && (
          <Box marginBottom={1} flexDirection="column">
            <Text bold color="green">
              Claude:
            </Text>
            <Text wrap="wrap">{currentStream || "..."}</Text>
          </Box>
        )}

        {/* Error */}
        {error && (
          <Box marginBottom={1}>
            <Text color="red">Error: {error}</Text>
          </Box>
        )}

        {/* Input */}
        <Box borderStyle="single" borderColor={streaming ? "gray" : "blue"} paddingX={1}>
          <Text>
            {streaming ? (
              <Text dimColor>Waiting for response...</Text>
            ) : (
              <>
                <Text color="blue">&gt; </Text>
                <Text>{inputText}</Text>
                <Text dimColor>|</Text>
              </>
            )}
          </Text>
        </Box>

        <Text dimColor>
          [Enter] send | [q] quit (when empty) | [Ctrl+C] force quit
        </Text>
      </Box>
    </Layout>
  );
}
