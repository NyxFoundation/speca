#!/usr/bin/env python3
"""Compare audit map findings against Sherlock CSV dataset with 3-stage matching."""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]


@dataclass
class Issue:
    issue_id: str
    title: str
    description: str
    text: str
    normalized: str
    tokens: set[str]


@dataclass
class AuditItem:
    item_id: str
    description: str
    snippet: str
    file: str
    line: str
    text: str
    normalized: str
    tokens: set[str]


def normalize_text(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9_]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def tokenize(text: str) -> set[str]:
    if not text:
        return set()
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_csv_issues(path: Path) -> list[Issue]:
    issues: list[Issue] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            title = (row.get("title") or "").strip()
            description = (row.get("description") or "").strip()
            issue_id = str(row.get("number") or "").strip()
            text = f"{title}\n{description}".strip()
            normalized = normalize_text(text)
            tokens = tokenize(text)
            issues.append(Issue(issue_id, title, description, text, normalized, tokens))
    return issues


def extract_audit_items(files: Iterable[Path]) -> list[AuditItem]:
    items: list[AuditItem] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        raw_items = payload.get("audit_items")
        if not isinstance(raw_items, list):
            continue
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("id") or "")
            description = str(raw.get("description") or "")
            snippet = str(raw.get("snippet") or "")
            file = str(raw.get("file") or "")
            line = str(raw.get("line") or "")
            text = "\n".join(part for part in [description, snippet, file, line] if part).strip()
            normalized = normalize_text(text)
            tokens = tokenize(text)
            items.append(AuditItem(item_id, description, snippet, file, line, text, normalized, tokens))
    return items


def select_top_candidates(audit_item: AuditItem, issues: list[Issue], top_k: int) -> list[Issue]:
    scored: list[tuple[float, Issue]] = []
    for issue in issues:
        score = jaccard(audit_item.tokens, issue.tokens)
        scored.append((score, issue))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [issue for score, issue in scored[:top_k] if score > 0.0]


def call_claude(prompt: str) -> str:
    result = subprocess.run(
        ["claude", "--output-format", "json", "-p", prompt],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def extract_json_from_text(text: str) -> dict | None:
    if not text:
        return None
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list) and payload:
            return payload[0] if isinstance(payload[0], dict) else None
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from Claude wrapper
    try:
        wrapper = json.loads(text)
        if isinstance(wrapper, dict) and "content" in wrapper:
            content = wrapper.get("content")
            if isinstance(content, list):
                combined = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            else:
                combined = str(content)
            match = re.search(r"\{.*\}", combined, flags=re.DOTALL)
            if match:
                return json.loads(match.group(0))
    except Exception:
        return None

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def llm_match(audit_item: AuditItem, candidates: list[Issue]) -> tuple[bool, str | None, float]:
    if not candidates:
        return False, None, 0.0

    candidate_block = []
    for idx, issue in enumerate(candidates):
        candidate_block.append(
            f"[{idx}] ID={issue.issue_id}\nTitle: {issue.title}\nDescription: {issue.description}\n"
        )

    prompt = (
        "You are matching security findings. Decide if the audit finding matches any candidate issue."
        " Respond with JSON only: {\"match\": true|false, \"candidate_index\": number|null, \"confidence\": 0-1}.\n\n"
        "Audit finding:\n"
        f"{audit_item.text}\n\n"
        "Candidates:\n"
        + "\n".join(candidate_block)
        + "\n"
    )

    raw = call_claude(prompt)
    payload = extract_json_from_text(raw) or {}
    match = bool(payload.get("match"))
    idx = payload.get("candidate_index")
    confidence = payload.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    if match and isinstance(idx, int) and 0 <= idx < len(candidates):
        return True, candidates[idx].issue_id, confidence
    return False, None, confidence


def parse_branches(value: str) -> list[str]:
    parts = [item.strip() for item in value.split(",")]
    return [p for p in parts if p]


def sanitize_branch(branch: str) -> str:
    return branch.replace("/", "__")


def match_branch(
    branch: str,
    issues: list[Issue],
    results_dir: Path,
    use_llm: bool,
    llm_max: int,
    stage1_threshold: float,
    stage2_threshold: float,
) -> dict:
    sanitized = sanitize_branch(branch)
    branch_dir = results_dir / sanitized
    files = sorted(branch_dir.glob("03_*.json"))
    audit_items = extract_audit_items(files)

    matches: dict[str, dict] = {}
    stage_counts = {"stage1": 0, "stage2": 0, "stage3": 0}
    llm_calls = 0

    for item in audit_items:
        best_score = 0.0
        best_issue = None
        for issue in issues:
            score = similarity(item.normalized, issue.normalized)
            if score > best_score:
                best_score = score
                best_issue = issue
        if best_issue and best_score >= stage1_threshold:
            matches[item.item_id] = {
                "stage": "stage1",
                "issue_id": best_issue.issue_id,
                "score": best_score,
            }
            stage_counts["stage1"] += 1

    for item in audit_items:
        if item.item_id in matches:
            continue
        best_score = 0.0
        best_issue = None
        for issue in issues:
            overlap = len(item.tokens & issue.tokens)
            score = jaccard(item.tokens, issue.tokens)
            if score > best_score and overlap >= 3:
                best_score = score
                best_issue = issue
        if best_issue and best_score >= stage2_threshold:
            matches[item.item_id] = {
                "stage": "stage2",
                "issue_id": best_issue.issue_id,
                "score": best_score,
            }
            stage_counts["stage2"] += 1

    if use_llm:
        for item in audit_items:
            if item.item_id in matches:
                continue
            if llm_calls >= llm_max:
                break
            candidates = select_top_candidates(item, issues, top_k=5)
            if not candidates:
                continue
            llm_calls += 1
            matched, issue_id, confidence = llm_match(item, candidates)
            if matched and issue_id:
                matches[item.item_id] = {
                    "stage": "stage3",
                    "issue_id": issue_id,
                    "score": confidence,
                }
                stage_counts["stage3"] += 1

    total = len(audit_items)
    matched_total = len(matches)
    new_total = total - matched_total
    overlap_rate = matched_total / total if total else 0.0
    new_rate = new_total / total if total else 0.0

    detail = {
        "branch": branch,
        "sanitized_branch": sanitized,
        "items_total": total,
        "matched_total": matched_total,
        "new_total": new_total,
        "overlap_rate": overlap_rate,
        "new_rate": new_rate,
        "stage_counts": stage_counts,
        "llm_used": use_llm,
        "llm_calls": llm_calls,
        "matches": matches,
    }

    detail_path = results_dir / f"evaluation_{sanitized}.json"
    detail_path.write_text(json.dumps(detail, indent=2), encoding="utf-8")
    return detail


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Sherlock dataset vs audit map outputs")
    parser.add_argument("--branches", required=True, help="Comma-separated branch names")
    parser.add_argument(
        "--csv",
        default=str(
            ROOT_DIR
            / "benchmarks"
            / "dataset"
            / "sherlock_ethereum_audit_contest"
            / "sherlock_contest_1140_issues_1766639267091.csv"
        ),
    )
    parser.add_argument(
        "--results-dir",
        default=str(ROOT_DIR / "benchmarks" / "results" / "sherlock_ethereum_audit_contest"),
    )
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--llm-max", type=int, default=200)
    parser.add_argument("--stage1-threshold", type=float, default=0.88)
    parser.add_argument("--stage2-threshold", type=float, default=0.25)
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    issues = load_csv_issues(Path(args.csv))

    summary = {
        "dataset": {
            "path": str(args.csv),
            "issues": len(issues),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "branches": {},
    }

    for branch in parse_branches(args.branches):
        detail = match_branch(
            branch,
            issues,
            results_dir,
            args.use_llm,
            args.llm_max,
            args.stage1_threshold,
            args.stage2_threshold,
        )
        summary["branches"][branch] = {
            "items_total": detail["items_total"],
            "matched_total": detail["matched_total"],
            "new_total": detail["new_total"],
            "overlap_rate": detail["overlap_rate"],
            "new_rate": detail["new_rate"],
            "stage_counts": detail["stage_counts"],
            "llm_used": detail["llm_used"],
            "llm_calls": detail["llm_calls"],
        }

    summary_path = results_dir / "evaluation_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
