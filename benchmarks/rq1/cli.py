#!/usr/bin/env python3
"""Compare audit map findings against Sherlock CSV dataset (CLI wrapper)."""
from __future__ import annotations

import argparse
from pathlib import Path

from benchmarks.rq1.evaluate import evaluate_branches, parse_branches

ROOT_DIR = Path(__file__).resolve().parents[1]


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
    args = parser.parse_args()
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    evaluate_branches(
        branches=parse_branches(args.branches),
        csv_path=Path(args.csv),
        results_dir=results_dir,
        use_llm=args.use_llm,
        llm_max=args.llm_max,
        stage1_threshold=args.stage1_threshold,
        stage2_threshold=args.stage2_threshold,
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
    )


if __name__ == "__main__":
    main()
