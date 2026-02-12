#!/usr/bin/env python3
"""Compare audit map findings against Sherlock CSV dataset (CLI wrapper)."""
from __future__ import annotations

import argparse
from pathlib import Path

from benchmarks.rq1.evaluate import evaluate_branches, parse_branches

ROOT_DIR = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Sherlock dataset vs audit map outputs")
    parser.add_argument("--branches", required=True, help="Comma-separated branch names")
    parser.add_argument(
        "--csv",
        default=str(
            ROOT_DIR
            / "benchmarks"
            / "data"
            / "rq1"
            / "sherlock_contest_1140_issues_1766639267091.csv"
        ),
    )
    parser.add_argument(
        "--results-dir",
        default=str(ROOT_DIR / "benchmarks" / "results" / "rq1" / "sherlock_ethereum_audit_contest"),
    )
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--llm-max", type=int, default=200)
    parser.add_argument("--stage1-threshold", type=float, default=0.88)
    parser.add_argument("--stage2-threshold", type=float, default=0.25)
    parser.add_argument("--keyword-min-overlap", type=int, default=2)
    parser.add_argument("--candidate-top-k", type=int, default=5)
    parser.add_argument("--baseline-results", type=str, default="", help="Baseline results dir with evaluation_*.json")
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=42)
    parser.add_argument("--ci-level", type=float, default=0.95)
    parser.add_argument("--human-scope", type=str, default="new_only", choices=["new_only", "all"])
    parser.add_argument("--human-sample-size", type=int, default=0)
    parser.add_argument("--human-sample-out", type=str, default="", help="Output path for human evaluation sample JSONL")
    parser.add_argument("--human-labels", type=str, default="", help="Human labels JSONL path")
    parser.add_argument("--human-labels-report", type=str, default="", help="Validation report output path (JSON)")
    parser.add_argument("--metadata", type=str, default="", help="Run metadata JSON to include in summary")
    parser.add_argument(
        "--audit-classifications",
        type=str,
        default="",
        help="Comma-separated audit classifications to include (e.g., exploitable,defense-in-depth)",
    )
    parser.add_argument(
        "--audit-include-bug-bounty",
        action="store_true",
        help="Include items marked bug_bounty_eligible regardless of classification filter",
    )
    parser.add_argument(
        "--client-filter",
        type=str,
        default="none",
        choices=["none", "auto", "keywords"],
        help="Filter issues to client-specific subset (auto infers from branch/target info)",
    )
    parser.add_argument(
        "--client-keywords",
        type=str,
        default="",
        help="Comma-separated keywords for issue filtering (used when client-filter=keywords or to override auto)",
    )
    args = parser.parse_args()
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    audit_classifications = {
        item.strip().lower()
        for item in args.audit_classifications.split(",")
        if item.strip()
    }
    if not audit_classifications:
        audit_classifications = None
    client_keywords = [item.strip() for item in args.client_keywords.split(",") if item.strip()]
    client_filter = args.client_filter
    if client_filter == "keywords" and not client_keywords:
        client_filter = "none"

    evaluate_branches(
        branches=parse_branches(args.branches),
        csv_path=Path(args.csv),
        results_dir=results_dir,
        use_llm=args.use_llm,
        llm_max=args.llm_max,
        stage1_threshold=args.stage1_threshold,
        stage2_threshold=args.stage2_threshold,
        keyword_min_overlap=args.keyword_min_overlap,
        candidate_top_k=args.candidate_top_k,
        baseline_dir=Path(args.baseline_results) if args.baseline_results else None,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
        ci_level=args.ci_level,
        human_scope=args.human_scope,
        human_sample_size=args.human_sample_size,
        human_sample_out=Path(args.human_sample_out) if args.human_sample_out else None,
        human_labels=Path(args.human_labels) if args.human_labels else None,
        human_labels_report=Path(args.human_labels_report) if args.human_labels_report else None,
        metadata_path=Path(args.metadata) if args.metadata else None,
        audit_classifications=audit_classifications,
        audit_include_bug_bounty=args.audit_include_bug_bounty,
        client_filter=client_filter,
        client_keywords=client_keywords,
    )


if __name__ == "__main__":
    main()
