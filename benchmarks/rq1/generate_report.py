#!/usr/bin/env python3
"""Generate a markdown summary for RQ1 evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_seconds(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if seconds < 60:
        return f"{seconds:.0f}s"
    return f"{seconds / 60:.1f}m"


def build_branch_env_table(branches: list[str], collection: dict) -> list[str]:
    manifests = {entry.get("branch"): entry for entry in collection.get("branches", [])}
    lines = [
        "| Branch | Commit | Phase 03 Runtime | Tokens (in/out/total) | Turns | Files |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for branch in branches:
        manifest = manifests.get(branch, {})
        target_info = manifest.get("target_info") or {}
        commit = (
            target_info.get("target_commit_short")
            or manifest.get("commit_short")
            or manifest.get("commit")
            or "n/a"
        )
        timing = manifest.get("phase_log_timing") or {}
        runtime = fmt_seconds(timing.get("estimated_total_seconds"))
        num_turns = timing.get("num_turns")
        num_turns_cell = str(num_turns) if isinstance(num_turns, (int, float)) else "n/a"
        tokens = timing.get("tokens") or {}
        token_in = tokens.get("input_tokens") or tokens.get("prompt_tokens") or 0
        token_out = tokens.get("output_tokens") or tokens.get("completion_tokens") or 0
        token_cache = (tokens.get("cache_read_input_tokens") or 0) + (tokens.get("cache_creation_input_tokens") or 0)
        token_total = tokens.get("total_tokens") or (token_in + token_out + token_cache)
        token_cell = f"{token_in}/{token_out}/{token_total}" if token_total else "n/a"
        files = str(len(manifest.get("files", []))) if manifest else "n/a"
        lines.append(f"| {branch} | {commit} | {runtime} | {token_cell} | {num_turns_cell} | {files} |")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate markdown summary for RQ1 evaluation")
    parser.add_argument("--summary", required=True, help="Path to evaluation_summary.json")
    parser.add_argument("--collection", default="", help="Path to collection_summary.json")
    parser.add_argument("--labels-csv", default="", help="Path to findings_labels.csv (recomputes precision)")
    parser.add_argument("--output", required=True, help="Output markdown path")
    args = parser.parse_args()

    summary_path = Path(args.summary)
    summary = load_json(summary_path)
    collection = load_json(Path(args.collection)) if args.collection else {}
    metadata = summary.get("run_metadata", {})

    # Recompute precision from labels CSV (picks up human labels)
    if args.labels_csv:
        labels_path = Path(args.labels_csv)
        if labels_path.exists():
            from benchmarks.rq1.evaluate import compute_precision

            prec = compute_precision(labels_path)
            summary["precision"] = prec
            recall = summary.get("recall", 0.0)
            if prec["precision_full"] > 0 and recall > 0:
                summary["f1"] = round(
                    2 * prec["precision_full"] * recall / (prec["precision_full"] + recall), 4,
                )
            else:
                summary["f1"] = 0.0
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# RQ1 Evaluation Report")
    lines.append("")
    lines.append(f"- Generated at (UTC): {summary.get('generated_at', 'unknown')}")
    dataset = summary.get("dataset", {})
    lines.append(f"- Dataset: {dataset.get('path', 'unknown')} ({dataset.get('issues_csv_total', '?')} issues in CSV)")
    lines.append(f"- Severity filter: {', '.join(summary.get('severity_filter', []))}")
    lines.append(f"- Audit classifications: {', '.join(summary.get('audit_classifications', []))}")
    lines.append(f"- Branches: {len(summary.get('branches', []))}")
    lines.append(f"- Audit findings: {summary.get('audit_items_total', 0)}")
    lines.append(f"- LLM calls: {summary.get('llm_calls', 0)}")
    lines.append("")

    # Environment
    lines.append("## Experiment Environment")
    ai = metadata.get("ai", {})
    ai_name = ai.get("name") or metadata.get("ai_name") or "unknown"
    ai_version = ai.get("version") or metadata.get("ai_version") or "unknown"
    lines.append(f"- AI: {ai_name} ({ai_version})")
    branches = summary.get("branches", [])
    if collection:
        lines.extend(build_branch_env_table(branches, collection))
    lines.append("")

    # Recall
    issues_total = summary.get("issues_total", 0)
    issues_matched = summary.get("issues_matched", 0)
    recall = summary.get("recall", 0.0)
    lines.append("## Recall")
    lines.append(f"**{issues_matched}/{issues_total} = {recall:.1%}**")
    lines.append("")

    # Severity breakdown
    breakdown = summary.get("severity_breakdown", {})
    if breakdown:
        lines.append("| Severity | Total | Matched | Recall |")
        lines.append("| --- | --- | --- | --- |")
        for sev in ["high", "medium", "low"]:
            stats = breakdown.get(sev, {})
            total = stats.get("total", 0)
            matched = stats.get("matched", 0)
            sev_recall = stats.get("recall", 0.0)
            lines.append(f"| {sev.capitalize()} | {total} | {matched} | {sev_recall:.1%} |")
        lines.append("")

    # Match details
    matches = summary.get("matches", {})
    if matches:
        lines.append("## Matched Issues")
        lines.append("| Issue # | Finding | Confidence |")
        lines.append("| --- | --- | --- |")
        for issue_id, info in sorted(matches.items(), key=lambda x: x[0]):
            finding_id = info.get("finding_id") or "?"
            confidence = info.get("confidence", 0.0)
            lines.append(f"| #{issue_id} | {finding_id} | {confidence:.2f} |")
        lines.append("")

    # Precision
    prec = summary.get("precision", {})
    if prec:
        lines.append("## Precision")
        total_findings = prec.get("total_findings", 0)
        auto_tp = prec.get("auto_tp", 0)
        auto_fp_invalid = prec.get("auto_fp_invalid", 0)
        auto_tp_info = prec.get("auto_tp_info", 0)
        auto_unknown = prec.get("auto_unknown", 0)
        human_tp = prec.get("human_tp", 0)
        human_fp = prec.get("human_fp", 0)
        precision_full = prec.get("precision_full", 0.0)
        precision_conservative = prec.get("precision_conservative", 0.0)
        lines.append(f"**Precision (labeled): {precision_full:.1%}** | Conservative (unknown=FP): {precision_conservative:.1%}")
        lines.append("")
        lines.append("| Category | Count | Precision role |")
        lines.append("| --- | --- | --- |")
        lines.append(f"| Total findings | {total_findings} | |")
        lines.append(f"| TP — H/M/L match (auto) | {auto_tp} | TP |")
        lines.append(f"| TP — info match (auto) | {auto_tp_info} | TP |")
        lines.append(f"| FP — invalid match (auto) | {auto_fp_invalid} | FP |")
        lines.append(f"| TP (human) | {human_tp} | TP |")
        lines.append(f"| FP (human) | {human_fp} | FP |")
        lines.append(f"| Unknown (unlabeled) | {auto_unknown} | — |")
        lines.append("")

    # F1
    f1 = summary.get("f1")
    if f1 is not None:
        lines.append("## F1 Score")
        lines.append(f"**F1 = {f1:.3f}** (recall={recall:.1%}, precision={prec.get('precision_full', 0.0):.1%})")
        lines.append("")

    # Missed issues
    missed = summary.get("missed_issues", [])
    if missed:
        lines.append("## Missed Issues")
        lines.append("| Issue # | Severity | Title |")
        lines.append("| --- | --- | --- |")
        for m in missed:
            lines.append(f"| #{m.get('issue_id', '?')} | {(m.get('severity') or '').capitalize()} | {m.get('title', '')} |")
        lines.append("")
    elif issues_total > issues_matched:
        lines.append("## Missed Issues")
        lines.append(f"{issues_total - issues_matched} issue(s) not matched by any audit finding.")
        lines.append("")

    # Metadata
    lines.append("## Raw Metadata")
    lines.append("```json")
    lines.append(json.dumps(metadata, indent=2))
    lines.append("```")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
