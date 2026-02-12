#!/usr/bin/env python3
"""Manual-ish evaluation: match audit items to CSV by report location (file/line) and client."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from benchmarks.rq1.evaluate import (
    filter_issues_by_keywords,
    infer_client_keywords,
    load_target_info,
    parse_branches,
    sanitize_branch,
)
from benchmarks.rq1.matchers import extract_classifications, load_csv_issues

ROOT_DIR = Path(__file__).resolve().parents[2]

FILE_EXT_RE = re.compile(
    r"\b[\w./-]+\.(rs|ts|go|py|java|cpp|c|h|kt|cs|sol|scala|rb|php|js|jsx|tsx)\b",
    re.IGNORECASE,
)
GITHUB_BLOB_RE = re.compile(
    r"https?://[^\s)]+?/blob/[^\s#]+/(?P<path>[^\s#]+?)#L(?P<line>\d+)(?:-L\d+)?",
    re.IGNORECASE,
)
LINE_RE = re.compile(r"\bline\s+(\d+)\b", re.IGNORECASE)


@dataclass
class IssueLoc:
    issue_id: str
    files: dict[str, set[int]]
    text: str


@dataclass
class AuditLoc:
    item_id: str
    file: str
    line: str


def extract_issue_locations(text: str) -> dict[str, set[int]]:
    files: dict[str, set[int]] = {}

    for match in GITHUB_BLOB_RE.finditer(text):
        path = match.group("path")
        line = match.group("line")
        basename = Path(path).name
        if not basename:
            continue
        files.setdefault(basename, set())
        try:
            files[basename].add(int(line))
        except ValueError:
            pass

    for match in FILE_EXT_RE.finditer(text):
        basename = Path(match.group(0)).name
        if not basename:
            continue
        files.setdefault(basename, set())

    for match in LINE_RE.finditer(text):
        line = match.group(1)
        try:
            line_int = int(line)
        except ValueError:
            continue
        for basename in files:
            files[basename].add(line_int)

    return files


def build_issue_index(issues) -> dict[str, IssueLoc]:
    index: dict[str, IssueLoc] = {}
    for issue in issues:
        text = f"{issue.title}\n{issue.description}".strip()
        files = extract_issue_locations(text)
        index[issue.issue_id] = IssueLoc(issue.issue_id, files, text)
    return index


def parse_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_selected_audit_item(raw: dict, classification_filter: set[str] | None) -> bool:
    if classification_filter is None:
        return True
    classifications = extract_classifications(raw)
    return bool(classifications & classification_filter)


def extract_audit_locations(files: Iterable[Path], classification_filter: set[str] | None) -> list[AuditLoc]:
    items: list[AuditLoc] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("audit_items"), list):
            raw_items = payload["audit_items"]
        elif isinstance(payload, list):
            raw_items = payload
        else:
            continue
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            if not is_selected_audit_item(raw, classification_filter):
                continue
            item_id = str(raw.get("id") or raw.get("check_id") or "")
            file = raw.get("file") or ""
            line = raw.get("line") or ""
            if not file and isinstance(raw.get("code_scope"), dict):
                file = raw["code_scope"].get("file") or ""
                if not line:
                    line = raw["code_scope"].get("line") or ""
            items.append(AuditLoc(item_id=item_id, file=str(file), line=str(line)))
    return items


def match_by_location(
    audit_items: list[AuditLoc],
    issue_index: dict[str, IssueLoc],
    line_window: int,
    ignore_lines: bool,
) -> tuple[dict[str, dict], dict]:
    matches: dict[str, dict] = {}
    stage_counts = {"stage1": 0, "stage2": 0, "stage3": 0}

    for item in audit_items:
        basename = Path(item.file).name if item.file else ""
        if not basename:
            continue
        audit_line = parse_int(item.line)

        best_issue = None
        best_stage = None
        best_distance = None

        for issue in issue_index.values():
            issue_lines = issue.files.get(basename)
            if issue_lines is None:
                continue
            if ignore_lines:
                if best_stage is None:
                    best_issue = issue.issue_id
                    best_stage = "stage2"
            elif audit_line is not None and issue_lines:
                distance = min(abs(audit_line - line) for line in issue_lines)
                if distance <= line_window:
                    if best_stage != "stage1" or (best_distance is not None and distance < best_distance):
                        best_issue = issue.issue_id
                        best_stage = "stage1"
                        best_distance = distance
            else:
                if best_stage is None:
                    best_issue = issue.issue_id
                    best_stage = "stage2"

        if best_issue and best_stage:
            matches[item.item_id] = {
                "stage": best_stage,
                "issue_id": best_issue,
                "score": 1.0 if best_stage == "stage1" else 0.5,
            }
            stage_counts[best_stage] += 1

    return matches, stage_counts


def evaluate_branches(
    branches: list[str],
    csv_path: Path,
    results_dir: Path,
    audit_classifications: set[str] | None,
    line_window: int,
    ignore_lines: bool,
    client_filter: str,
    client_keywords: list[str],
) -> None:
    issues = load_csv_issues(csv_path)

    summary = {
        "dataset": {"path": str(csv_path), "issues": len(issues)},
        "branches": {},
        "match_config": {"line_window": line_window, "method": "file_line"},
        "audit_item_filter": {
            "classifications": sorted(audit_classifications) if audit_classifications else None,
        },
        "issue_filter": {"mode": client_filter, "keywords": client_keywords or None},
    }

    overall_matched_issue_ids: set[str] = set()
    overall_issue_candidates: set[str] = set()

    for branch in branches:
        sanitized = sanitize_branch(branch)
        target_info = load_target_info(results_dir, sanitized)

        branch_keywords = client_keywords
        if client_filter == "auto" and not client_keywords:
            branch_keywords = infer_client_keywords(branch, target_info)

        filtered_issues = issues
        if client_filter != "none" and branch_keywords:
            filtered_issues = filter_issues_by_keywords(issues, branch_keywords)

        issue_index = build_issue_index(filtered_issues)
        overall_issue_candidates.update(issue_index.keys())

        files = sorted((results_dir / sanitized).glob("03_*.json"))
        audit_items = extract_audit_locations(files, audit_classifications)

        matches, stage_counts = match_by_location(audit_items, issue_index, line_window, ignore_lines)
        total = len(audit_items)
        matched_total = len(matches)
        new_total = total - matched_total
        overlap_rate = matched_total / total if total else 0.0
        new_rate = new_total / total if total else 0.0
        matched_issue_ids = {match["issue_id"] for match in matches.values()}
        issues_matched_total = len(matched_issue_ids)
        issue_recall = issues_matched_total / len(filtered_issues) if filtered_issues else 0.0

        detail = {
            "branch": branch,
            "sanitized_branch": sanitized,
            "items_total": total,
            "matched_total": matched_total,
            "new_total": new_total,
            "overlap_rate": overlap_rate,
            "new_rate": new_rate,
            "issues_matched_total": issues_matched_total,
            "issue_recall": issue_recall,
            "stage_counts": stage_counts,
            "llm_used": False,
            "llm_calls": 0,
            "matches": matches,
        }

        detail_path = results_dir / f"evaluation_{sanitized}.json"
        detail_path.write_text(json.dumps(detail, indent=2), encoding="utf-8")

        summary["branches"][branch] = {
            "items_total": total,
            "matched_total": matched_total,
            "new_total": new_total,
            "overlap_rate": overlap_rate,
            "new_rate": new_rate,
            "issues_matched_total": issues_matched_total,
            "issue_recall": issue_recall,
            "issues_total": len(filtered_issues),
            "stage_counts": stage_counts,
            "llm_used": False,
            "llm_calls": 0,
            "issue_filter": {
                "mode": client_filter,
                "keywords": branch_keywords if branch_keywords else None,
                "target_repo": target_info.get("target_repo") if isinstance(target_info, dict) else None,
            },
        }

        overall_matched_issue_ids.update(matched_issue_ids)

    summary["issues_matched_total"] = len(overall_matched_issue_ids)
    summary["issues_total"] = len(overall_issue_candidates) if overall_issue_candidates else len(issues)
    summary["issue_recall"] = (
        len(overall_matched_issue_ids) / summary["issues_total"] if summary["issues_total"] else 0.0
    )

    summary_path = results_dir / "evaluation_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual evaluation by location match")
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
    parser.add_argument(
        "--audit-classifications",
        type=str,
        default="",
        help="Comma-separated audit classifications to include",
    )
    parser.add_argument("--line-window", type=int, default=20)
    parser.add_argument("--ignore-lines", action="store_true")
    parser.add_argument(
        "--client-filter",
        type=str,
        default="auto",
        choices=["none", "auto", "keywords"],
    )
    parser.add_argument("--client-keywords", type=str, default="")
    args = parser.parse_args()

    audit_classifications = {
        item.strip().lower() for item in args.audit_classifications.split(",") if item.strip()
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
        results_dir=Path(args.results_dir),
        audit_classifications=audit_classifications,
        line_window=args.line_window,
        ignore_lines=args.ignore_lines,
        client_filter=client_filter,
        client_keywords=client_keywords,
    )


if __name__ == "__main__":
    main()
