/**
 * `speca ask` chat surface (M5).
 *
 * Layout follows docs/SPECA_CLI_SPEC.md §5.5:
 *
 *   ┌─ Header                         ─┐
 *   ├─ Conversation                   ─┤   (scrollable list of MessageBubbles)
 *   ├─ Streaming indicator (optional) ─┤
 *   ├─ Input                          ─┤
 *   └──────────────────────────────────┘
 *
 * Modal keybindings (only the navigation set; the input box owns its own
 * key handling while it is active — see ChatInput):
 *   - normal mode: i / a → enter input mode
 *   - normal mode: ↑ / ↓ → scroll messages
 *   - normal mode: c     → toggle context modal
 *   - normal mode: n     → start a new session (clears session.json on disk)
 *   - normal mode: q     → exit (saves session)
 *   - input mode:  Esc   → back to normal mode
 *   - input mode:  Ctrl-D / Ctrl-Enter → submit
 */

import { Box, Text, useApp, useInput } from "ink";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ChatInput } from "./ChatInput.js";
import { Layout } from "./Layout.js";
import { MessageBubble, type MessageRole } from "./MessageBubble.js";
import { StreamingIndicator } from "./StreamingIndicator.js";
import {
  composeAskPrompt,
  DEFAULT_MAX_CONTEXT_BYTES,
  type FindingContextInput,
} from "../lib/claude-session/context.js";
import { spawnAsk, type ParsedEvent } from "../lib/claude-session/spawn.js";
import {
  clearSession,
  loadSession,
  newSessionInfo,
  saveSession,
  sessionFilePath,
  touchSessionInfo,
  type SessionInfo,
} from "../lib/claude-session/store.js";

interface ChatMessage {
  id: number;
  role: MessageRole;
  text: string;
  /** True while the assistant is still streaming this turn. */
  pending?: boolean;
}

export interface AskChatProps {
  /** Loaded finding context (or null for a session without one). */
  finding: FindingContextInput | null;
  /** Pretty label for the finding (e.g. "PROP-abc-001 (HIGH)"). */
  findingLabel?: string;
  /** Override the project root (for tests). */
  projectRoot?: string;
  /** Override the resolved session id (e.g. when --session is passed). */
  initialSessionId?: string;
  /** Max bytes of context to inject. */
  maxContextBytes?: number;
  /**
   * Spawn function override. Tests can pass a fake that yields canned events
   * without ever launching a real subprocess. Defaults to the real spawnAsk.
   */
  spawnFn?: typeof spawnAsk;
}

let nextMsgId = 1;
function makeId(): number {
  return nextMsgId++;
}

export function AskChat({
  finding,
  findingLabel,
  projectRoot = process.cwd(),
  initialSessionId,
  maxContextBytes = DEFAULT_MAX_CONTEXT_BYTES,
  spawnFn,
}: AskChatProps) {
  const { exit } = useApp();
  const spawnImpl = spawnFn ?? spawnAsk;

  const [sessionId, setSessionId] = useState<string | undefined>(initialSessionId);
  const [sessionLoaded, setSessionLoaded] = useState(false);
  const [contextBytesLast, setContextBytesLast] = useState(0);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [mode, setMode] = useState<"normal" | "input">("input");
  const [busy, setBusy] = useState(false);
  const [scrollOffset, setScrollOffset] = useState(0);
  const [showContext, setShowContext] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Resolve the session id on mount, unless one was provided via CLI flag.
  useEffect(() => {
    let cancelled = false;
    if (initialSessionId) {
      setSessionLoaded(true);
      return () => {
        cancelled = true;
      };
    }
    loadSession(projectRoot)
      .then((info) => {
        if (cancelled) return;
        if (info) setSessionId(info.session_id);
        setSessionLoaded(true);
      })
      .catch(() => {
        if (cancelled) return;
        setSessionLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [initialSessionId, projectRoot]);

  // Persist session changes (on best-effort; never block UI on disk errors).
  const persistSession = useCallback(
    async (sid: string, ctxBytes: number) => {
      try {
        const existing = await loadSession(projectRoot);
        const info: SessionInfo = existing
          ? touchSessionInfo({ ...existing, session_id: sid }, ctxBytes)
          : newSessionInfo(sid, ctxBytes);
        await saveSession(info, projectRoot);
      } catch {
        // ignore
      }
    },
    [projectRoot],
  );

  const sendQuestion = useCallback(
    async (question: string): Promise<void> => {
      const trimmed = question.trim();
      if (trimmed.length === 0) return;
      const userId = makeId();
      const assistantId = makeId();
      setMessages((prev) => [
        ...prev,
        { id: userId, role: "user", text: trimmed },
        { id: assistantId, role: "assistant", text: "", pending: true },
      ]);
      setBusy(true);
      setError(null);

      // First turn injects context; subsequent turns let --resume keep state.
      const isFirstTurn = !sessionId;
      const includeContext = isFirstTurn && !!finding;
      const composed = composeAskPrompt(includeContext ? finding : null, trimmed, {
        maxBytes: maxContextBytes,
      });
      const ctxBytes = composed.context?.bytes ?? 0;
      if (includeContext) setContextBytesLast(ctxBytes);

      let handle;
      try {
        handle = await spawnImpl({
          prompt: composed.prompt,
          sessionId,
        });
      } catch (err) {
        const m = (err as Error).message;
        setError(m);
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantId ? { ...msg, text: `(spawn failed: ${m})`, pending: false } : msg,
          ),
        );
        setBusy(false);
        return;
      }

      let learnedSessionId: string | undefined = sessionId;
      let assistantText = "";
      try {
        for await (const ev of handle.events as AsyncIterable<ParsedEvent>) {
          if (ev.type === "assistant" && ev.text.length > 0) {
            assistantText += ev.text;
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantId ? { ...msg, text: assistantText, pending: true } : msg,
              ),
            );
          }
          if ((ev.type === "system" || ev.type === "assistant" || ev.type === "result") && ev.session_id) {
            learnedSessionId = ev.session_id;
          }
          if (ev.type === "stderr") {
            // Surface stderr via console.error per spec; don't pollute chat.
            // (Ink will redraw — not pretty but acceptable for diagnostics.)
            // eslint-disable-next-line no-console
            console.error(`[claude stderr] ${ev.line}`);
          }
          if (ev.type === "spawn-error") {
            setError(ev.message);
          }
          if (ev.type === "done") {
            break;
          }
        }
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantId
              ? { ...msg, text: assistantText || "(no response)", pending: false }
              : msg,
          ),
        );
        setBusy(false);
        if (learnedSessionId) {
          setSessionId(learnedSessionId);
          await persistSession(learnedSessionId, ctxBytes);
        }
      }
    },
    [finding, maxContextBytes, persistSession, sessionId, spawnImpl],
  );

  // Normal-mode key handling (ChatInput owns input-mode keys).
  useInput(
    (input, key) => {
      if (showContext) {
        if (key.escape || input === "c" || input === "q") setShowContext(false);
        return;
      }
      if (mode === "normal") {
        if (input === "i" || input === "a") {
          setMode("input");
          return;
        }
        if (input === "q" || (key.ctrl && (input === "c" || input === "C"))) {
          exit();
          return;
        }
        if (input === "c") {
          setShowContext(true);
          return;
        }
        if (input === "n") {
          // New session: drop in-memory id + delete disk file. Subsequent
          // sendQuestion will inject context anew.
          setSessionId(undefined);
          setMessages([]);
          clearSession(projectRoot).catch(() => {
            // ignore
          });
          return;
        }
        if (key.upArrow) setScrollOffset((n) => Math.max(0, n - 1));
        if (key.downArrow) setScrollOffset((n) => n + 1);
      }
    },
    { isActive: !busy || showContext },
  );

  const headerRight = useMemo(() => {
    const sid = sessionId ? `${sessionId.slice(0, 8)}…` : "new";
    const finding = findingLabel ?? "(no finding)";
    return `finding: ${finding}   session: ${sid}`;
  }, [findingLabel, sessionId]);

  const onSubmit = useCallback(
    (text: string): void => {
      setMode("normal");
      void sendQuestion(text);
    },
    [sendQuestion],
  );

  const onCancelInput = useCallback(() => {
    setMode("normal");
  }, []);

  // Scrolling: render a window over `messages` using `scrollOffset`. We keep
  // the whole list in memory; the offset just controls what's visible.
  const visibleMessages = useMemo(() => {
    if (scrollOffset === 0) return messages;
    const cut = Math.min(scrollOffset, Math.max(0, messages.length - 1));
    return messages.slice(0, messages.length - cut);
  }, [messages, scrollOffset]);

  return (
    <Layout title="speca ask" status={`${headerRight}   ${sessionLoaded ? "" : "(loading session…)"}`}>
      <Box flexDirection="column">
        {messages.length === 0 ? (
          <Text dimColor>
            {finding
              ? "Ask a question about this finding. Press 'i' for input mode, 'q' to quit."
              : "Ask a question. Press 'i' for input mode, 'q' to quit."}
          </Text>
        ) : (
          visibleMessages.map((m) => (
            <MessageBubble key={m.id} role={m.role} text={m.text} streaming={m.pending} />
          ))
        )}
        {busy ? <StreamingIndicator /> : null}
        {error ? (
          <Box marginTop={1}>
            <Text color="red">error: {error}</Text>
          </Box>
        ) : null}
        {showContext ? (
          <Box marginTop={1} borderStyle="round" paddingX={1} flexDirection="column">
            <Text bold>Context (injected on first turn)</Text>
            <Text dimColor>finding: {findingLabel ?? "(none)"}</Text>
            <Text dimColor>last context bytes: {contextBytesLast}</Text>
            <Text dimColor>cap: {maxContextBytes} bytes</Text>
            <Text dimColor>session.json: {sessionFilePath(projectRoot)}</Text>
            <Text dimColor>(press c or Esc to close)</Text>
          </Box>
        ) : null}
        <Box marginTop={1}>
          <ChatInput
            active={mode === "input" && !busy}
            placeholder={mode === "input" ? "Type your question…" : "(press 'i' to type)"}
            onSubmit={onSubmit}
            onCancel={onCancelInput}
          />
        </Box>
        <Box marginTop={0}>
          <Text dimColor>
            mode: {mode}{busy ? " (busy)" : ""} · [i] input · [c] context · [n] new session · [q] quit
          </Text>
        </Box>
      </Box>
    </Layout>
  );
}
