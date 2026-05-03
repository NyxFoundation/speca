/**
 * Pure key-descriptor matcher. Decoupled from Ink so it can be unit-tested
 * against fixture `Key` objects.
 *
 * A key descriptor is one of:
 *   - `"q"` — single character, matches when `input` equals that character.
 *   - `"escape" | "return" | "tab" | "backspace" | "delete" |
 *      "upArrow" | "downArrow" | "leftArrow" | "rightArrow" |
 *      "pageUp" | "pageDown" | "home" | "end"` — matches the corresponding
 *      Ink `Key` boolean flag.
 *   - `"ctrl+x"` — matches when `key.ctrl` is true and `input` equals `"x"`
 *     (case-insensitive on the letter).
 */

export interface KeyEvent {
  ctrl?: boolean;
  meta?: boolean;
  shift?: boolean;
  escape?: boolean;
  return?: boolean;
  tab?: boolean;
  backspace?: boolean;
  delete?: boolean;
  upArrow?: boolean;
  downArrow?: boolean;
  leftArrow?: boolean;
  rightArrow?: boolean;
  pageUp?: boolean;
  pageDown?: boolean;
  home?: boolean;
  end?: boolean;
}

const NAMED_FLAGS: Array<keyof KeyEvent> = [
  "escape",
  "return",
  "tab",
  "backspace",
  "delete",
  "upArrow",
  "downArrow",
  "leftArrow",
  "rightArrow",
  "pageUp",
  "pageDown",
  "home",
  "end",
];

const NAMED_FLAG_SET = new Set<string>(NAMED_FLAGS);

/**
 * Test whether `(input, key)` matches the descriptor `descriptor`.
 *
 * Returns `false` (never throws) on unknown descriptors so a typo in
 * `config.toml` becomes a dead binding rather than a crash.
 */
export function matchKey(descriptor: string, input: string, key: KeyEvent): boolean {
  if (!descriptor) return false;
  const desc = descriptor.trim();
  if (!desc) return false;

  // ctrl+<letter>
  if (desc.toLowerCase().startsWith("ctrl+")) {
    if (!key.ctrl) return false;
    const letter = desc.slice("ctrl+".length).toLowerCase();
    if (letter.length === 0) return false;
    return input.toLowerCase() === letter;
  }

  // Named flag (escape, return, etc).
  if (NAMED_FLAG_SET.has(desc)) {
    return Boolean(key[desc as keyof KeyEvent]);
  }

  // Single-character descriptor — must match input exactly. Ignore when the
  // event also carries a modifier like ctrl, otherwise `q` would fire on
  // ctrl+q.
  if (desc.length === 1) {
    if (key.ctrl || key.meta) return false;
    return input === desc;
  }

  return false;
}

/**
 * Convenience wrapper: returns true if any descriptor in `descriptors`
 * matches the `(input, key)` pair.
 */
export function matchAny(descriptors: string[], input: string, key: KeyEvent): boolean {
  for (const d of descriptors) {
    if (matchKey(d, input, key)) return true;
  }
  return false;
}
