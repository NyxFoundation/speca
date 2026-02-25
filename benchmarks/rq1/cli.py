#!/usr/bin/env python3
"""RQ1 evaluation CLI — issue recall measurement."""
from __future__ import annotations

import argparse
from pathlib import Path

from benchmarks.rq1.evaluate import evaluate, parse_branches

ROOT_DIR = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description="RQ1: measure issue recall (H/M/L)")
    parser.add_argument("--branches", required=True, help="Comma-separated branch names")
    parser.add_argument(
        "--csv",
        default=str(
            ROOT_DIR / "benchmarks" / "data" / "rq1"
            / "sherlock_contest_1140_issues_1766639267091.csv"
        ),
    )
    parser.add_argument(
        "--results-dir",
        default=str(ROOT_DIR / "benchmarks" / "results" / "rq1" / "sherlock_ethereum_audit_contest"),
    )
    parser.add_argument(
        "--severity-filter",
        default="high,medium,low",
        help="Comma-separated severity levels for denominator",
    )
    parser.add_argument(
        "--audit-classifications",
        default="vulnerability,potential-vulnerability",
        help="Comma-separated audit classifications to include",
    )
    parser.add_argument("--metadata", default="", help="Run metadata JSON path")
    parser.add_argument(
        "--reparse", action="store_true", default=False,
        help="Re-parse cached LLM responses without calling LLM",
    )
    parser.add_argument(
        "--label", action="store_true", default=False,
        help="Generate findings_labels.csv with auto FP detection for precision measurement",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    severity_filter = {s.strip().lower() for s in args.severity_filter.split(",") if s.strip()}
    audit_classifications = {s.strip().lower() for s in args.audit_classifications.split(",") if s.strip()}
    if not audit_classifications:
        audit_classifications = None

    evaluate(
        branches=parse_branches(args.branches),
        csv_path=Path(args.csv),
        results_dir=results_dir,
        severity_filter=severity_filter,
        audit_classifications=audit_classifications,
        metadata_path=Path(args.metadata) if args.metadata else None,
        reparse=args.reparse,
        label=args.label,
    )


if __name__ == "__main__":
    main()
