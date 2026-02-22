#!/usr/bin/env python3
"""Generate visualization charts from RQ2 benchmark metrics."""

from __future__ import annotations

import json
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_METRICS = ROOT_DIR / "benchmarks" / "results" / "rq2" / "metrics.json"
OUTPUT_DIR = ROOT_DIR / "benchmarks" / "results" / "rq2" / "figures"

TOOL_DISPLAY = {
    "semgrep": "Semgrep",
    "codeql": "CodeQL",
    "security_agent": "Security Agent",
    "llm_baseline": "LLM Baseline",
    "static_baseline": "Static Baseline",
}

TOOL_COLORS = {
    "semgrep": "#4CAF50",
    "codeql": "#2196F3",
    "security_agent": "#FF5722",
    "llm_baseline": "#9C27B0",
    "static_baseline": "#607D8B",
}

STATUS_COLORS = {
    "ok": "#4CAF50",
    "missing_results": "#BDBDBD",
    "invalid_results": "#FF9800",
}


def load_metrics(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fig1_tool_comparison(data: dict, output_dir: Path) -> None:
    """Bar chart comparing tool precision, recall, F1."""
    tools = data.get("tools", {})
    tool_names = []
    precision_vals = []
    recall_vals = []
    f1_vals = []
    coverage_vals = []

    for name, metrics in tools.items():
        if metrics.get("status") != "ok":
            continue
        tool_names.append(TOOL_DISPLAY.get(name, name))
        precision_vals.append(metrics.get("precision", 0))
        recall_vals.append(metrics.get("recall", 0))
        f1_vals.append(metrics.get("f1", 0))
        coverage_vals.append(metrics.get("coverage", 0))

    if not tool_names:
        print("  No tools with results to plot for fig1")
        return

    x = np.arange(len(tool_names))
    width = 0.2

    fig, ax = plt.subplots(figsize=(10, 6))
    bars1 = ax.bar(x - 1.5 * width, precision_vals, width, label="Precision", color="#2196F3")
    bars2 = ax.bar(x - 0.5 * width, recall_vals, width, label="Recall", color="#FF5722")
    bars3 = ax.bar(x + 0.5 * width, f1_vals, width, label="F1", color="#4CAF50")
    bars4 = ax.bar(x + 1.5 * width, coverage_vals, width, label="Coverage", color="#9C27B0", alpha=0.6)

    ax.set_xlabel("Tool")
    ax.set_ylabel("Score")
    ax.set_title("RQ2: Tool Performance Comparison (PrimeVul Dataset)")
    ax.set_xticks(x)
    ax.set_xticklabels(tool_names)
    ax.legend()
    ax.set_ylim(0, 1.1)
    ax.grid(axis="y", alpha=0.3)

    # Add value labels on bars
    for bars in [bars1, bars2, bars3, bars4]:
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.annotate(f"{height:.2f}", xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    fig.savefig(output_dir / "fig1_tool_comparison.png", dpi=150)
    plt.close(fig)
    print(f"  Saved fig1_tool_comparison.png")


def fig2_confusion_matrix(data: dict, output_dir: Path) -> None:
    """Stacked bar chart showing confusion matrix breakdown for each tool."""
    tools = data.get("tools", {})
    tool_names = []
    tp_vals = []
    fp_vals = []
    tn_vals = []
    fn_vals = []

    for name, metrics in tools.items():
        if metrics.get("status") != "ok":
            continue
        scored = metrics.get("tp", 0) + metrics.get("fp", 0) + metrics.get("tn", 0) + metrics.get("fn", 0)
        if scored == 0:
            continue
        tool_names.append(TOOL_DISPLAY.get(name, name))
        tp_vals.append(metrics.get("tp", 0))
        fp_vals.append(metrics.get("fp", 0))
        tn_vals.append(metrics.get("tn", 0))
        fn_vals.append(metrics.get("fn", 0))

    if not tool_names:
        print("  No tools with confusion data for fig2")
        return

    x = np.arange(len(tool_names))
    width = 0.5

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.bar(x, tp_vals, width, label="TP (True Positive)", color="#4CAF50")
    ax.bar(x, fp_vals, width, bottom=tp_vals, label="FP (False Positive)", color="#FF9800")
    ax.bar(x, tn_vals, width, bottom=[tp + fp for tp, fp in zip(tp_vals, fp_vals)],
           label="TN (True Negative)", color="#2196F3")
    ax.bar(x, fn_vals, width,
           bottom=[tp + fp + tn for tp, fp, tn in zip(tp_vals, fp_vals, tn_vals)],
           label="FN (False Negative)", color="#F44336")

    ax.set_xlabel("Tool")
    ax.set_ylabel("Number of Samples")
    ax.set_title("RQ2: Confusion Matrix Breakdown")
    ax.set_xticks(x)
    ax.set_xticklabels(tool_names)
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.3)

    # Add total annotation
    for i, (tp, fp, tn, fn) in enumerate(zip(tp_vals, fp_vals, tn_vals, fn_vals)):
        total = tp + fp + tn + fn
        ax.annotate(f"n={total}", xy=(i, total), xytext=(0, 5),
                    textcoords="offset points", ha="center", fontsize=9, fontweight="bold")

    fig.tight_layout()
    fig.savefig(output_dir / "fig2_confusion_matrix.png", dpi=150)
    plt.close(fig)
    print(f"  Saved fig2_confusion_matrix.png")


def fig3_cwe_coverage(data: dict, output_dir: Path) -> None:
    """Horizontal bar chart showing CWE coverage for top CWEs."""
    dataset = data.get("dataset", {})
    tools = data.get("tools", {})
    cwe_totals = dataset.get("cwe_totals", {})

    if not cwe_totals:
        print("  No CWE data for fig3")
        return

    # Top 15 CWEs by count
    top_cwes = sorted(cwe_totals.items(), key=lambda x: x[1], reverse=True)[:15]
    cwe_names = [cwe for cwe, _ in top_cwes]
    cwe_counts = [count for _, count in top_cwes]

    fig, ax = plt.subplots(figsize=(12, 8))

    # Background bars (total vulnerable count)
    y = np.arange(len(cwe_names))
    bars = ax.barh(y, cwe_counts, color="#E0E0E0", label="Total Vulnerable")

    # Overlay per-tool TP counts
    active_tools = [(name, metrics) for name, metrics in tools.items()
                    if metrics.get("status") == "ok" and metrics.get("cwe_coverage")]

    for tool_idx, (tool_name, metrics) in enumerate(active_tools):
        cwe_cov = metrics.get("cwe_coverage", {})
        tp_counts = [cwe_cov.get(cwe, {}).get("tp", 0) for cwe in cwe_names]
        if any(tp > 0 for tp in tp_counts):
            offset = (tool_idx + 1) * 0.15
            ax.barh(y + offset, tp_counts, height=0.15,
                    color=TOOL_COLORS.get(tool_name, "#999"),
                    label=f"{TOOL_DISPLAY.get(tool_name, tool_name)} TP")

    # Labels
    for i, (cwe, count) in enumerate(zip(cwe_names, cwe_counts)):
        ax.text(count + 0.5, i, str(count), va="center", fontsize=9)

    ax.set_yticks(y)
    ax.set_yticklabels(cwe_names)
    ax.set_xlabel("Number of Vulnerable Samples")
    ax.set_title("RQ2: CWE Distribution & Tool Detection Coverage (PrimeVul)")
    ax.legend(loc="lower right")
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_dir / "fig3_cwe_coverage.png", dpi=150)
    plt.close(fig)
    print(f"  Saved fig3_cwe_coverage.png")


def fig4_tool_status(data: dict, output_dir: Path) -> None:
    """Summary diagram showing tool status and dataset overview."""
    tools = data.get("tools", {})
    dataset = data.get("dataset", {})

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Left: Tool status
    ax1 = axes[0]
    tool_names = list(tools.keys())
    statuses = [tools[t].get("status", "unknown") for t in tool_names]
    colors = [STATUS_COLORS.get(s, "#999") for s in statuses]
    display_names = [TOOL_DISPLAY.get(t, t) for t in tool_names]

    y = np.arange(len(tool_names))
    ax1.barh(y, [1] * len(tool_names), color=colors, height=0.6)
    for i, (name, status) in enumerate(zip(display_names, statuses)):
        label = "Ready" if status == "ok" else status.replace("_", " ").title()
        ax1.text(0.5, i, f"{name}\n({label})", ha="center", va="center",
                fontsize=10, fontweight="bold", color="white" if status == "ok" else "black")
    ax1.set_xlim(0, 1)
    ax1.set_yticks([])
    ax1.set_xticks([])
    ax1.set_title("Tool Status")
    ax1.invert_yaxis()

    # Right: Dataset composition
    ax2 = axes[1]
    gt_count = dataset.get("ground_truth_count", 0)
    total = dataset.get("sample_count", 0)

    # Count vuln vs clean from tools data
    semgrep = tools.get("semgrep", {})
    tp = semgrep.get("tp", 0)
    fn = semgrep.get("fn", 0)
    fp = semgrep.get("fp", 0)
    tn = semgrep.get("tn", 0)
    vuln_count = tp + fn
    clean_count = fp + tn

    if vuln_count + clean_count > 0:
        sizes = [vuln_count, clean_count]
        labels = [f"Vulnerable\n({vuln_count})", f"Clean\n({clean_count})"]
        colors = ["#F44336", "#4CAF50"]
        explode = (0.05, 0)
        wedges, texts, autotexts = ax2.pie(sizes, labels=labels, colors=colors,
                                            autopct="%1.1f%%", explode=explode,
                                            startangle=90, textprops={"fontsize": 11})
        ax2.set_title(f"Dataset Composition (n={total})")
    else:
        ax2.text(0.5, 0.5, f"Total: {total} samples\nGround truth: {gt_count}",
                ha="center", va="center", fontsize=14, transform=ax2.transAxes)
        ax2.set_title("Dataset Overview")

    fig.suptitle("RQ2 Benchmark Overview: PrimeVul Dataset", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(output_dir / "fig4_overview.png", dpi=150)
    plt.close(fig)
    print(f"  Saved fig4_overview.png")


def fig5_cwe_treemap(data: dict, output_dir: Path) -> None:
    """Bubble chart showing CWE distribution by count."""
    cwe_totals = data.get("dataset", {}).get("cwe_totals", {})
    if not cwe_totals:
        print("  No CWE data for fig5")
        return

    # Sort by count
    sorted_cwes = sorted(cwe_totals.items(), key=lambda x: x[1], reverse=True)
    cwes = [c for c, _ in sorted_cwes[:20]]
    counts = [n for _, n in sorted_cwes[:20]]

    fig, ax = plt.subplots(figsize=(14, 8))

    # Create bubble positions
    np.random.seed(42)
    n = len(cwes)
    cols = 5
    rows = (n + cols - 1) // cols
    x_pos = []
    y_pos = []
    for i in range(n):
        x_pos.append((i % cols) * 3)
        y_pos.append((i // cols) * 3)

    max_count = max(counts)
    sizes = [(c / max_count) * 3000 + 200 for c in counts]

    # Color by severity (higher count = more red)
    colors = plt.cm.RdYlGn_r(np.array(counts) / max_count)

    scatter = ax.scatter(x_pos, y_pos, s=sizes, c=colors, alpha=0.7, edgecolors="black", linewidth=0.5)

    for i, (cwe, count) in enumerate(zip(cwes, counts)):
        ax.annotate(f"{cwe}\n({count})", (x_pos[i], y_pos[i]),
                    ha="center", va="center", fontsize=8, fontweight="bold")

    ax.set_xlim(-2, cols * 3)
    ax.set_ylim(-2, rows * 3)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("RQ2: CWE Distribution in PrimeVul (Top 20)", fontsize=14, fontweight="bold")

    fig.tight_layout()
    fig.savefig(output_dir / "fig5_cwe_distribution.png", dpi=150)
    plt.close(fig)
    print(f"  Saved fig5_cwe_distribution.png")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate RQ2 visualization charts.")
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    if not args.metrics.exists():
        print(f"Metrics file not found: {args.metrics}")
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    data = load_metrics(args.metrics)
    print(f"Loaded metrics from {args.metrics}")

    print("Generating figures...")
    fig1_tool_comparison(data, args.output_dir)
    fig2_confusion_matrix(data, args.output_dir)
    fig3_cwe_coverage(data, args.output_dir)
    fig4_tool_status(data, args.output_dir)
    fig5_cwe_distribution(data, args.output_dir)

    print(f"\nAll figures saved to {args.output_dir}/")
    return 0


# Alias for consistent naming
fig5_cwe_distribution = fig5_cwe_treemap


if __name__ == "__main__":
    raise SystemExit(main())
