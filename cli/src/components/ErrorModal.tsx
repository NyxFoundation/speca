/**
 * Generic error modal used by the M3 dashboard, M4 finding browser, and
 * M5 ask-Claude pane. The component is read-only — the `onDismiss` /
 * `onRetry` callbacks are wired by the parent screen so the modal stays
 * decoupled from app navigation.
 *
 * Layout:
 *
 *   ┌────────────────────────────────────────┐
 *   │ x  Authentication expired              │
 *   │                                        │
 *   │ Token refresh returned 401.            │
 *   │                                        │
 *   │ Hint: Run `speca auth login` to ...    │
 *   │                                        │
 *   │ [enter] dismiss   [r] retry            │
 *   └────────────────────────────────────────┘
 *
 * Colour comes from the active Theme; icon is paired with severity colour
 * so `NO_COLOR=1` users still get a visible cue (SPEC §10.8).
 */

import { Box, Text } from "ink";
import { useTheme } from "../lib/theme/index.js";
import { getErrorKindMeta, type ErrorKind } from "../lib/errors/kinds.js";

export interface ErrorModalProps {
  kind: ErrorKind;
  /** Optional override of the kind's `defaultTitle`. */
  title?: string;
  /** Body message — typically the upstream error string. */
  message: string;
  /** Optional override of the kind's `defaultHint`. */
  hint?: string;
  /**
   * Dismiss callback. The modal does not bind keys itself — wire this to
   * `useKeybind("cancel"|"confirm", onDismiss)` in the parent screen so
   * the parent owns input focus management.
   */
  onDismiss?: () => void;
  /**
   * Optional retry callback. When provided, the modal renders a `[r]
   * retry` hint in its footer. Same focus-management caveat as
   * `onDismiss`.
   */
  onRetry?: () => void;
}

function severityColor(theme: ReturnType<typeof useTheme>, severity: "error" | "warn" | "info"): string {
  switch (severity) {
    case "error":
      return theme.colors.error;
    case "warn":
      return theme.colors.warn;
    case "info":
      return theme.colors.info;
  }
}

export function ErrorModal({ kind, title, message, hint, onDismiss, onRetry }: ErrorModalProps) {
  const theme = useTheme();
  const meta = getErrorKindMeta(kind);
  const headColor = severityColor(theme, meta.severity);
  const resolvedTitle = title ?? meta.defaultTitle;
  const resolvedHint = hint ?? meta.defaultHint;

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={headColor}
      paddingX={1}
      paddingY={0}
    >
      <Box>
        <Text color={headColor} bold>
          {meta.icon} {resolvedTitle}
        </Text>
      </Box>
      <Box marginTop={1}>
        <Text color={theme.colors.text}>{message}</Text>
      </Box>
      <Box marginTop={1}>
        <Text color={theme.colors.muted}>Hint: {resolvedHint}</Text>
      </Box>
      <Box marginTop={1}>
        <Text color={theme.colors.dim}>
          {onDismiss ? "[enter] dismiss" : ""}
          {onDismiss && onRetry ? "   " : ""}
          {onRetry ? "[r] retry" : ""}
        </Text>
      </Box>
    </Box>
  );
}
