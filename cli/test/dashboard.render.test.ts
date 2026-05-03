import { describe, expect, it } from "vitest";
import { render } from "ink-testing-library";
import { createElement } from "react";
import { Dashboard } from "../src/components/Dashboard.js";
import { PipelineStore } from "../src/lib/pipeline/store.js";

const ts = "2026-05-03T12:00:00.000+00:00";

describe("Dashboard rendering", () => {
  it("renders the empty state before any events arrive", () => {
    const store = new PipelineStore();
    const ui = render(createElement(Dashboard, { store, cwd: "/tmp/proj" }));
    const out = ui.lastFrame();
    expect(out).toContain("speca run");
    expect(out).toContain("project: /tmp/proj");
    expect(out).toContain("(no phases registered yet)");
    ui.unmount();
  });

  it("shows phase rows with status glyphs after events arrive", () => {
    const store = new PipelineStore();
    store.applyEvent({
      type: "pipeline-started",
      ts,
      phases: ["01a", "01b"],
      workers: 4,
      max_concurrent: 8,
      force: false,
    });
    store.applyEvent({
      type: "phase-started",
      ts,
      phase: "01a",
      workers: 4,
      max_concurrent: 8,
      force: false,
      model: "sonnet",
    });
    store.applyEvent({
      type: "phase-completed",
      ts,
      phase: "01a",
      duration_s: 1,
      total_results: 3,
    });
    const ui = render(createElement(Dashboard, { store, cwd: "/tmp/proj" }));
    const out = ui.lastFrame() ?? "";
    expect(out).toContain("01a");
    expect(out).toContain("Spec Discovery");
    expect(out).toContain("[OK]");
    expect(out).toContain("01b");
    expect(out).toContain("[ ]");
    ui.unmount();
  });

  it("shows the failed status for a failed phase", () => {
    const store = new PipelineStore();
    store.applyEvent({
      type: "pipeline-started",
      ts,
      phases: ["01b"],
      workers: 4,
      max_concurrent: 8,
      force: false,
    });
    store.applyEvent({
      type: "phase-failed",
      ts,
      phase: "01b",
      reason: "dependency check failed",
      duration_s: 0.1,
    });
    const ui = render(createElement(Dashboard, { store, cwd: "/tmp/proj" }));
    const out = ui.lastFrame() ?? "";
    expect(out).toContain("[X]");
    expect(out).toContain("dependency check failed");
    ui.unmount();
  });

  it("shows the budget-exceeded modal", () => {
    const store = new PipelineStore();
    store.applyEvent({
      type: "pipeline-started",
      ts,
      phases: ["03"],
      workers: 4,
      max_concurrent: 8,
      force: false,
    });
    store.applyEvent({
      type: "budget-exceeded",
      ts,
      phase: "03",
      cost_usd: 9.99,
      max_budget_usd: 10,
      duration_s: 600,
    });
    const ui = render(createElement(Dashboard, { store, cwd: "/tmp/proj" }));
    const out = ui.lastFrame() ?? "";
    expect(out).toContain("Budget exceeded");
    expect(out).toContain("$9.99");
    expect(out).toContain("$10.00");
    ui.unmount();
  });

  it("shows live log lines in the log pane", () => {
    const store = new PipelineStore();
    store.applyEvent({
      type: "pipeline-started",
      ts,
      phases: ["01a"],
      workers: 4,
      max_concurrent: 8,
      force: false,
    });
    store.applyLog({
      phase: "01a",
      worker: "0",
      batch: "1",
      ts,
      type: "assistant",
      summary: "tool_use: Grep",
      severity: "info",
      tool: "Grep",
      sourcePath: "/tmp/log.jsonl",
    });
    const ui = render(createElement(Dashboard, { store, cwd: "/tmp/proj" }));
    const out = ui.lastFrame() ?? "";
    expect(out).toContain("Live log");
    expect(out).toContain("[01a/W0/B1]");
    expect(out).toContain("tool_use: Grep");
    ui.unmount();
  });

  it("status bar lists the documented key bindings", () => {
    const store = new PipelineStore();
    const ui = render(createElement(Dashboard, { store, cwd: "/tmp/proj" }));
    const out = ui.lastFrame() ?? "";
    expect(out).toContain("Enter");
    expect(out).toContain("stop");
    expect(out).toContain("force");
    expect(out).toContain("toggle log");
    expect(out).toContain("quit");
    ui.unmount();
  });
});
