import { describe, expect, it, vi } from "vitest";

/**
 * When no Python core can be located (broken install: no vendor/, no
 * checkout, no SPECA_ROOT) the default spawn path must fail through the same
 * observable channel as a missing `uv` binary — a `spawn-error` event plus a
 * non-zero exit — instead of throwing synchronously into the run command.
 *
 * resolveCoreRoot is mocked to throw because a real "not found" cannot be
 * reproduced from inside the speca checkout (the dev fallback always finds
 * the repo root).
 */
vi.mock("../src/lib/core-root.js", () => ({
  isCoreRoot: () => false,
  resolveCoreRoot: () => {
    throw new Error(
      "speca: cannot locate the bundled Python core. Run `speca doctor`.",
    );
  },
}));

import { spawnPipeline } from "../src/lib/pipeline/spawn.js";

describe("spawnPipeline — unresolvable core root", () => {
  it("emits spawn-error and resolves done with 127", async () => {
    const handle = spawnPipeline({ phases: ["01a"] });
    let error: Error | null = null;
    let exit: { code: number; signal: NodeJS.Signals | null } | null = null;
    handle.on("spawn-error", (err) => {
      error = err;
    });
    handle.on("exit", (code, signal) => {
      exit = { code, signal };
    });

    const code = await handle.done;
    expect(code).toBe(127);
    expect(exit).toEqual({ code: 127, signal: null });
    expect(error).not.toBeNull();
    expect(error!.message).toContain("speca doctor");
    expect(handle.pid).toBeUndefined();
  });

  it("still surfaces the argument-validation throw before core resolution", () => {
    // Programmer error stays synchronous — unchanged contract.
    expect(() => spawnPipeline({})).toThrowError(/either `phases` or `target`/);
  });
});
