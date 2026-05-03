/**
 * Default keybinds for speca-cli. Each action maps to one or more key
 * descriptors that the keybinds layer matches against `useInput` events.
 *
 * Key descriptor grammar:
 *   - A single printable character: `"q"`, `"j"`, `"/"`
 *   - An Ink modifier name: `"escape"`, `"return"`, `"tab"`,
 *     `"upArrow"`, `"downArrow"`, `"leftArrow"`, `"rightArrow"`,
 *     `"backspace"`, `"delete"`, `"pageUp"`, `"pageDown"`
 *   - A `ctrl+<key>` chord: `"ctrl+c"`, `"ctrl+l"` (case-insensitive on the
 *     letter portion).
 *
 * Action names are kebab-case and used both as the key in `config.toml`
 * (`[keybinds]` table) and as the `action` argument to `useKeybind`.
 */

export const DEFAULT_KEYBINDS: Record<string, string[]> = {
  // Quit / cancel — present on every screen.
  exit: ["q", "ctrl+c"],
  // Dismiss a modal without quitting.
  cancel: ["escape"],
  // Confirm a modal action.
  confirm: ["return"],
  // Trigger an optional retry on an error modal.
  retry: ["r"],
  // Generic navigation.
  up: ["upArrow", "k"],
  down: ["downArrow", "j"],
  left: ["leftArrow", "h"],
  right: ["rightArrow", "l"],
  pageUp: ["pageUp"],
  pageDown: ["pageDown"],
  // Pipeline dashboard (M3) — show / hide log pane.
  "toggle-log": ["l"],
  // Finding browser (M4) — enter filter-edit mode.
  "filter-mode": ["f"],
  // Finding browser (M4) — cycle sort key.
  "sort-mode": ["s"],
  // Ask Claude (M5) — focus the chat input.
  "focus-chat": ["i"],
  // Help overlay (any screen).
  help: ["?"],
};
