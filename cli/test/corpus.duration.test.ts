/**
 * parseDuration — tiny <int><unit> format used by `corpus gc --older-than`.
 */
import { describe, expect, it } from "vitest";

import { parseDuration } from "../src/lib/corpus/duration.js";

describe("parseDuration", () => {
  it.each([
    ["30s", 30_000],
    ["5m", 300_000],
    ["1h", 3_600_000],
    ["1d", 86_400_000],
    ["2w", 1_209_600_000],
    ["  90d  ", 90 * 86_400_000],
    ["7D", 7 * 86_400_000],
  ])("parses %s", (raw, expected) => {
    expect(parseDuration(raw)).toBe(expected);
  });

  it.each([
    "",
    "abc",
    "0d",
    "-1d",
    "1y",
    "1 d 2 h",
    "1.5d",
    "d",
  ])("rejects %s", (raw) => {
    expect(() => parseDuration(raw)).toThrow();
  });
});
