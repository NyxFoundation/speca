#!/usr/bin/env python3
"""Generate a Markdown report from benchmark metrics."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_METRICS = ROOT_DIR / "benchmarks" / "results" / "rq2" / "metrics.json"
DEFAULT_REPORT = ROOT_DIR / "benchmarks" / "results" / "rq2" / "report.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate benchmark report.")
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--rq1-summary", type=Path, default=None, help="RQ1 evaluation_summary.json")
    return parser.parse_args()


def format_metric(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def format_ci(ci: dict | None) -> str:
    if not ci:
        return "n/a"
    low, high = ci.get("ci", [None, None])
    if low is None or high is None:
        return "n/a"
    return f"[{low:.3f}, {high:.3f}]"


def main() -> int:
    args = parse_args()
    if not args.metrics.exists():
        print(f"Metrics file not found: {args.metrics}")
        return 1

    data = json.loads(args.metrics.read_text(encoding="utf-8"))
    rq1_data = None
    if args.rq1_summary and args.rq1_summary.exists():
        rq1_data = json.loads(args.rq1_summary.read_text(encoding="utf-8"))
    dataset = data.get("dataset", {})
    tools = data.get("tools", {})
    comparisons = data.get("comparisons", {})
    unique = comparisons.get("unique_detections", {}).get("security_agent_only", {})

    lines = []
    lines.append("# Benchmark Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append("## Dataset")
    lines.append("")
    lines.append(f"- Path: {dataset.get('path', 'unknown')}")
    lines.append(f"- Ground-truth samples: {dataset.get('ground_truth_count', 0)}")
    lines.append(f"- Total samples: {dataset.get('sample_count', 0)}")
    lines.append(
        f"- Pair groups: {dataset.get('pair_count', 0)} (eligible: {dataset.get('pair_eligible', 0)}, skipped: {dataset.get('pair_skipped', 0)})"
    )
    lines.append("")
    lines.append("## Tool Metrics")
    lines.append("")
    lines.append("| Tool | Precision | Recall | F1 | Coverage | TP | FP | TN | FN | Errors |")
    lines.append("| ---- | --------- | ------ | -- | -------- | -- | -- | -- | -- | ------ |")

    for tool, metrics in tools.items():
        if metrics.get("status") != "ok":
            lines.append(f"| {tool} | n/a | n/a | n/a | 0.000 | 0 | 0 | 0 | 0 | 0 |")
            continue
        lines.append(
            "| {tool} | {precision} | {recall} | {f1} | {coverage} | {tp} | {fp} | {tn} | {fn} | {errors} |".format(
                tool=tool,
                precision=format_metric(metrics.get("precision")),
                recall=format_metric(metrics.get("recall")),
                f1=format_metric(metrics.get("f1")),
                coverage=format_metric(metrics.get("coverage")),
                tp=metrics.get("tp", 0),
                fp=metrics.get("fp", 0),
                tn=metrics.get("tn", 0),
                fn=metrics.get("fn", 0),
                errors=metrics.get("error_count", 0),
            )
        )

    lines.append("")
    lines.append("## Tool Metadata")
    lines.append("")
    tool_metadata = data.get("tool_metadata", {})
    if tool_metadata:
        lines.append("| Tool | Version | Timeout | Limit |")
        lines.append("| ---- | ------- | ------- | ----- |")
        for tool, meta in tool_metadata.items():
            lines.append(
                "| {tool} | {version} | {timeout} | {limit} |".format(
                    tool=tool,
                    version=(meta.get("version") or "n/a").replace("\n", " "),
                    timeout=meta.get("timeout_sec", "n/a"),
                    limit=meta.get("limit", "n/a"),
                )
            )
    else:
        lines.append("- n/a")
    lines.append("")
    lines.append("## Pairwise Correct")
    lines.append("")
    lines.append("## Pairwise Statistics (Security Agent vs Baselines)")
    lines.append("")
    pairwise_stats = comparisons.get("pairwise_stats", {})
    if pairwise_stats:
        lines.append("| Baseline | n | McNemar p | Cliff's delta | Effect | Acc diff (CI) | F1 diff (CI) |")
        lines.append("| -------- | - | --------- | ------------- | ------ | ------------- | ------------ |")
        for baseline, stats in pairwise_stats.items():
            diffs = stats.get("metric_diffs", {})
            lines.append(
                "| {baseline} | {n} | {p} | {delta} | {effect} | {acc_ci} | {f1_ci} |".format(
                    baseline=baseline,
                    n=stats.get("n", 0),
                    p=format_metric(stats.get("mcnemar_p")),
                    delta=format_metric(stats.get("effect_size", {}).get("paired_proportion_diff", stats.get("effect_size", {}).get("cliffs_delta"))),
                    effect=stats.get("effect_size", {}).get("magnitude", "n/a"),
                    acc_ci=format_ci(diffs.get("accuracy")),
                    f1_ci=format_ci(diffs.get("f1")),
                )
            )
    else:
        lines.append("- n/a")
    lines.append("")
    lines.append("| Tool | Accuracy | Correct | Scored | Total | Skipped |")
    lines.append("| ---- | -------- | ------- | ------ | ----- | ------- |")
    for tool, metrics in tools.items():
        pairwise = metrics.get("pairwise")
        if not pairwise:
            lines.append(f"| {tool} | n/a | 0 | 0 | 0 | 0 |")
            continue
        lines.append(
            "| {tool} | {accuracy} | {correct} | {scored} | {total} | {skipped} |".format(
                tool=tool,
                accuracy=format_metric(pairwise.get("accuracy")),
                correct=pairwise.get("correct", 0),
                scored=pairwise.get("scored", 0),
                total=pairwise.get("total", 0),
                skipped=pairwise.get("skipped", 0),
            )
        )
    lines.append("")
    lines.append("## Unique Detections (Security Agent)")
    lines.append("")
    if unique:
        lines.append(f"- Count: {unique.get('count', 0)}")
        compared = unique.get("compared_against", [])
        if compared:
            lines.append(f"- Compared against: {', '.join(compared)}")
        by_cwe = unique.get("by_cwe", {})
        if by_cwe:
            lines.append("")
            lines.append("| CWE | Count |")
            lines.append("| --- | ----- |")
            for cwe, info in sorted(by_cwe.items(), key=lambda item: item[1].get("count", 0), reverse=True)[:10]:
                lines.append(f"| {cwe} | {info.get('count', 0)} |")
    else:
        lines.append("- n/a")
    lines.append("")
    lines.append("## CWE Coverage (Top 10 by vulnerable count)")
    lines.append("")
    cwe_totals = dataset.get("cwe_totals", {})
    if cwe_totals:
        top_cwes = sorted(cwe_totals.items(), key=lambda item: item[1], reverse=True)[:10]
        lines.append("| CWE | Total | Semgrep Recall | CodeQL Recall | Security Agent Recall |")
        lines.append("| --- | ----- | -------------- | ------------- | --------------------- |")
        for cwe, total in top_cwes:
            lines.append(
                "| {cwe} | {total} | {semgrep} | {codeql} | {agent} |".format(
                    cwe=cwe,
                    total=total,
                    semgrep=format_metric(tools.get("semgrep", {}).get("cwe_coverage", {}).get(cwe, {}).get("recall")),
                    codeql=format_metric(tools.get("codeql", {}).get("cwe_coverage", {}).get(cwe, {}).get("recall")),
                    agent=format_metric(
                        tools.get("security_agent", {}).get("cwe_coverage", {}).get(cwe, {}).get("recall")
                    ),
                )
            )
    else:
        lines.append("- n/a")
    lines.append("")
    lines.append("## Traditional Tool Weaknesses (Missed CWE)")
    lines.append("")
    for tool in ("semgrep", "codeql"):
        missed = tools.get(tool, {}).get("missed_by_cwe", {})
        if not missed:
            lines.append(f"- {tool}: n/a")
            continue
        top_missed = sorted(missed.items(), key=lambda item: item[1], reverse=True)[:5]
        entries = ", ".join(f"{cwe} ({count})" for cwe, count in top_missed)
        lines.append(f"- {tool}: {entries}")
    lines.append("")
    lines.append("## Example Cases (Security Agent Only)")
    lines.append("")
    examples = unique.get("examples", []) if unique else []
    if not examples:
        lines.append("- n/a")
    else:
        for idx, example in enumerate(examples, start=1):
            lines.append(f"### Example {idx}: {example.get('id', 'unknown')}")
            lines.append("")
            cwes = example.get("cwe") or []
            if cwes:
                lines.append(f"- CWE: {', '.join(cwes)}")
            cve = example.get("cve")
            if cve:
                lines.append(f"- CVE: {cve}")
            path = example.get("path")
            if path:
                lines.append(f"- Path: {path}")
            spec = example.get("spec_evidence")
            if spec:
                lines.append(f"- Spec evidence: {spec}")
            else:
                lines.append("- Spec evidence: n/a")
            code = example.get("code_snippet")
            if code:
                language = example.get("language") or ""
                lines.append("")
                lines.append(f"```{language}")
                lines.append(code)
                lines.append("```")
            lines.append("")

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    for tool, metrics in tools.items():
        if metrics.get("status") == "missing_results":
            lines.append(f"- {tool}: results missing.")
            continue
        if metrics.get("coverage", 0) == 0:
            lines.append(f"- {tool}: no scored samples (check runner configuration).")
            continue

        skipped_pred = metrics.get("skipped_missing_pred", 0)
        skipped_gt = metrics.get("skipped_missing_gt", 0)
        if skipped_pred or skipped_gt:
            lines.append(
                f"- {tool}: skipped {skipped_pred} samples without predictions and {skipped_gt} samples missing ground truth."
            )

    if rq1_data:
        lines.append("")
        lines.append("## RQ1 (Sherlock) Summary")
        lines.append("")
        lines.append(f"- Issues CSV: {rq1_data.get('dataset', {}).get('path', 'unknown')}")
        branches = rq1_data.get("branches", {})
        if branches:
            lines.append("")
            lines.append("| Branch | Items | Overlap | New | Overlap CI | New CI | LLM Calls |")
            lines.append("| ------ | ----- | ------- | --- | ---------- | ------ | --------- |")
            for branch, info in branches.items():
                lines.append(
                    "| {branch} | {items} | {overlap} | {new} | {overlap_ci} | {new_ci} | {llm} |".format(
                        branch=branch,
                        items=info.get("items_total", 0),
                        overlap=format_metric(info.get("overlap_rate")),
                        new=format_metric(info.get("new_rate")),
                        overlap_ci=format_ci(info.get("overlap_rate_ci")),
                        new_ci=format_ci(info.get("new_rate_ci")),
                        llm=info.get("llm_calls", 0),
                    )
                )
        else:
            lines.append("- No branches found.")

        baseline_notes = []
        for branch, info in branches.items():
            baseline = info.get("baseline_comparison")
            if not baseline:
                continue
            baseline_notes.append(
                "{branch}: p={p}, delta={d} ({m})".format(
                    branch=branch,
                    p=format_metric(baseline.get("mcnemar_p")),
                    d=format_metric(baseline.get("effect_size", {}).get("paired_proportion_diff", baseline.get("effect_size", {}).get("cliffs_delta"))),
                    m=baseline.get("effect_size", {}).get("magnitude", "n/a"),
                )
            )
        if baseline_notes:
            lines.append("")
            lines.append("Baseline comparisons:")
            for note in baseline_notes:
                lines.append(f"- {note}")

        human_eval = rq1_data.get("human_eval")
        if human_eval:
            lines.append("")
            lines.append("Human evaluation:")
            lines.append(
                "- scope={scope}, labeled={labeled}, precision={precision}, CI={ci}, invalid_rows={invalid}".format(
                    scope=human_eval.get("scope", "n/a"),
                    labeled=human_eval.get("labeled_total", 0),
                    precision=format_metric(human_eval.get("precision")),
                    ci=format_ci(human_eval.get("precision_ci")),
                    invalid=human_eval.get("invalid_label_rows", 0),
                )
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote report to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
