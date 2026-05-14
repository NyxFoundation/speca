/**
 * Tiny duration parser for `--older-than` style flags.
 *
 * Supports a single segment of the form `<int><suffix>`:
 *   - `s` seconds, `m` minutes, `h` hours, `d` days, `w` weeks
 *
 * Examples: `90d`, `2w`, `36h`, `30m`, `300s`. Whitespace around the value
 * is tolerated; negative numbers are rejected.
 */
const UNIT_MS: Record<string, number> = {
  s: 1_000,
  m: 60_000,
  h: 3_600_000,
  d: 86_400_000,
  w: 604_800_000,
};

export function parseDuration(raw: string): number {
  const s = (raw ?? "").trim().toLowerCase();
  const m = /^(\d+)\s*(s|m|h|d|w)$/u.exec(s);
  if (!m) {
    throw new Error(
      `invalid duration ${JSON.stringify(raw)} — expected <integer><unit> ` +
        `where unit is one of s,m,h,d,w (e.g. 90d, 2w, 36h)`,
    );
  }
  const n = Number.parseInt(m[1] ?? "0", 10);
  const unit = (m[2] ?? "") as keyof typeof UNIT_MS;
  if (!Number.isFinite(n) || n <= 0) {
    throw new Error(`invalid duration ${raw} — value must be a positive integer`);
  }
  return n * UNIT_MS[unit];
}
