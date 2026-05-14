/**
 * archiveRoot() — precedence rules between CLI arg, env, and the default
 * `<cwd>/.speca/runs` path.
 */
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { archiveRoot } from "../src/lib/corpus/paths.js";

const PREV_ENV = process.env.SPECA_ARCHIVE_ROOT;
let prevCwd: string;

beforeEach(() => {
  prevCwd = process.cwd();
  delete process.env.SPECA_ARCHIVE_ROOT;
});

afterEach(() => {
  process.chdir(prevCwd);
  if (PREV_ENV === undefined) delete process.env.SPECA_ARCHIVE_ROOT;
  else process.env.SPECA_ARCHIVE_ROOT = PREV_ENV;
});

describe("archiveRoot", () => {
  it("uses explicit CLI override when provided", () => {
    expect(archiveRoot("/tmp/x")).toBe(resolve("/tmp/x"));
  });

  it("trims whitespace from the explicit override", () => {
    expect(archiveRoot("  /tmp/x  ")).toBe(resolve("/tmp/x"));
  });

  it("falls back to SPECA_ARCHIVE_ROOT env when no explicit override", () => {
    process.env.SPECA_ARCHIVE_ROOT = "/tmp/from-env";
    expect(archiveRoot()).toBe(resolve("/tmp/from-env"));
  });

  it("ignores empty env value", () => {
    process.env.SPECA_ARCHIVE_ROOT = "   ";
    const expected = resolve(process.cwd(), ".speca", "runs");
    expect(archiveRoot()).toBe(expected);
  });

  it("defaults to <cwd>/.speca/runs when nothing is set", () => {
    delete process.env.SPECA_ARCHIVE_ROOT;
    const expected = resolve(process.cwd(), ".speca", "runs");
    expect(archiveRoot()).toBe(expected);
  });

  it("CLI override beats env", () => {
    process.env.SPECA_ARCHIVE_ROOT = "/tmp/from-env";
    expect(archiveRoot("/tmp/explicit")).toBe(resolve("/tmp/explicit"));
  });
});
