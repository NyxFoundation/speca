import { describe, it, expect } from "vitest";

// We test the arg builder logic by importing and inspecting the module.
// The actual spawn is hard to unit-test without a real Python env, so we
// focus on the event parsing (covered in events.test.ts) and arg construction.

describe("process-bridge buildArgs (via module internals)", () => {
  // Since buildArgs is not exported, we test the integration points instead.
  // This test validates that the module can be imported without errors.
  it("module imports cleanly", async () => {
    const mod = await import("../src/lib/process-bridge.js");
    expect(mod.spawnPipeline).toBeDefined();
    expect(typeof mod.spawnPipeline).toBe("function");
  });
});
