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
    minutes = seconds / 60
    return f"{minutes:.1f}m"


def build_branch_env_table(summary: dict, collection: dict) -> list[str]:
    manifests = {entry.get("branch"): entry for entry in collection.get("branches", [])}
    lines = [
        "| Branch | Commit | Phase 03 Runtime | Tokens (in/out/total) | Files |",
        "| --- | --- | --- | --- | --- |",
    ]
    for branch in summary.get("branches", {}).keys():
        manifest = manifests.get(branch, {})
        target_info = manifest.get("target_info") or {}
        commit = target_info.get("target_commit_short") or manifest.get("commit_short") or manifest.get("commit") or "n/a"
        timing = manifest.get("phase_log_timing") or {}
        runtime = fmt_seconds(timing.get("estimated_total_seconds"))
        tokens = timing.get("tokens") or {}
        token_in = tokens.get("input_tokens") or tokens.get("prompt_tokens") or 0
        token_out = tokens.get("output_tokens") or tokens.get("completion_tokens") or 0
        token_cache = (tokens.get("cache_read_input_tokens") or 0) + (tokens.get("cache_creation_input_tokens") or 0)
        token_total = tokens.get("total_tokens") or (token_in + token_out + token_cache)
        token_cell = f"{token_in}/{token_out}/{token_total}" if token_total else "n/a"
        files = str(len(manifest.get("files", []))) if manifest else "n/a"
        lines.append(f"| {branch} | {commit} | {runtime} | {token_cell} | {files} |")
    return lines


def build_results_table(summary: dict) -> list[str]:
    lines = [
        "| Branch | Items | Matched | Overlap | Issues Matched | Issue Recall | New | LLM Calls |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for branch, stats in summary.get("branches", {}).items():
        overlap = f"{stats.get('overlap_rate', 0.0):.3f}"
        recall = f"{stats.get('issue_recall', 0.0):.3f}"
        lines.append(
            "| {branch} | {items_total} | {matched_total} | {overlap} | {issues_matched_total} | {recall} | {new_total} | {llm_calls} |".format(
                branch=branch,
                items_total=stats.get("items_total", 0),
                matched_total=stats.get("matched_total", 0),
                overlap=overlap,
                issues_matched_total=stats.get("issues_matched_total", 0),
                recall=recall,
                new_total=stats.get("new_total", 0),
                llm_calls=stats.get("llm_calls", 0),
            )
        )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate markdown summary for RQ1 evaluation")
    parser.add_argument("--summary", required=True, help="Path to evaluation_summary.json")
    parser.add_argument("--collection", default="", help="Path to collection_summary.json")
    parser.add_argument("--output", required=True, help="Output markdown path")
    args = parser.parse_args()

    summary = load_json(Path(args.summary))
    collection = load_json(Path(args.collection)) if args.collection else {}
    metadata = summary.get("run_metadata", {})
    match_config = summary.get("match_config", {})

    lines = []
    lines.append("# RQ1 Evaluation Report")
    lines.append("")
    lines.append(f"- Generated at (UTC): {summary.get('generated_at', 'unknown')}")
    dataset = summary.get("dataset", {})
    lines.append(f"- Dataset: {dataset.get('path', 'unknown')} ({dataset.get('issues', 0)} issues)")
    lines.append("")

    lines.append("## Experiment Environment")
    ai = metadata.get("ai", {})
    ai_name = ai.get("name") or metadata.get("ai_name") or "unknown"
    ai_version = ai.get("version") or metadata.get("ai_version") or "unknown"
    lines.append(f"- AI: {ai_name} ({ai_version})")
    if collection:
        lines.extend(build_branch_env_table(summary, collection))
    else:
        lines.append("- Targets: collection_summary.json not provided")
    lines.append("")

    lines.append("## Matching & Recall")
    lines.append(
        "- Keyword matching against CSV issues selects candidate issues; LLM judges semantic similarity for final match."
    )
    lines.append(
        "- Recall definition: issue_recall = unique_issue_ids_matched / total_issues_in_csv (per branch)."
    )
    lines.append(
        "- unique_issue_ids_matched is computed from matched audit items' issue_id values."
    )
    if match_config:
        lines.append(
            "- Match config: "
            + ", ".join(
                f"{key}={value}"
                for key, value in match_config.items()
                if value is not None and value != ""
            )
        )
    lines.append("")

    lines.append("## Results")
    lines.extend(build_results_table(summary))
    lines.append("")
    if "issue_recall" in summary:
        lines.append(
            f"- Overall issue recall (union of branches): {summary.get('issue_recall', 0.0):.3f} "
            f"({summary.get('issues_matched_total', 0)}/{dataset.get('issues', 0)})"
        )
    lines.append("")

    lines.append("## Raw Metadata")
    lines.append("```json")
    lines.append(json.dumps(metadata, indent=2))
    lines.append("```")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
