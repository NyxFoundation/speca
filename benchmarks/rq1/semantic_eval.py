#!/usr/bin/env python3
"""Approximate semantic evaluation using TF-IDF cosine similarity."""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
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
from benchmarks.rq1.matchers import extract_classifications, load_csv_issues, normalize_text, tokenize

ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass
class IssueDoc:
    issue_id: str
    text: str
    tokens: list[str]


@dataclass
class AuditDoc:
    item_id: str
    text: str
    tokens: list[str]
    file: str


def is_selected_audit_item(raw: dict, classification_filter: set[str] | None) -> bool:
    if classification_filter is None:
        return True
    classifications = extract_classifications(raw)
    return bool(classifications & classification_filter)


def extract_audit_docs(files: Iterable[Path], classification_filter: set[str] | None) -> list[AuditDoc]:
    items: list[AuditDoc] = []
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
            if not file and isinstance(raw.get("code_scope"), dict):
                file = raw["code_scope"].get("file") or ""
            description = str(raw.get("description") or raw.get("summary") or raw.get("reason") or "")
            title = str(raw.get("title") or "")
            snippet = str(raw.get("snippet") or "")
            text = "\n".join(part for part in (title, description, snippet, file) if part).strip()
            tokens = list(tokenize(text))
            items.append(AuditDoc(item_id=item_id, text=text, tokens=tokens, file=file))
    return items


def build_issue_docs(issues) -> list[IssueDoc]:
    docs: list[IssueDoc] = []
    for issue in issues:
        text = f"{issue.title}\n{issue.description}".strip()
        tokens = list(tokenize(text))
        docs.append(IssueDoc(issue.issue_id, text=text, tokens=tokens))
    return docs


def compute_idf(docs: list[list[str]]) -> dict[str, float]:
    df: Counter[str] = Counter()
    for tokens in docs:
        for token in set(tokens):
            df[token] += 1
    n = len(docs)
    idf = {token: math.log((n + 1) / (df_val + 1)) + 1.0 for token, df_val in df.items()}
    return idf


def tf_idf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    if not tokens:
        return {}
    tf = Counter(tokens)
    vec: dict[str, float] = {}
    for token, count in tf.items():
        weight = (count / len(tokens)) * idf.get(token, 0.0)
        if weight:
            vec[token] = weight
    return vec


def cosine_sim(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = 0.0
    for token, weight in a.items():
        if token in b:
            dot += weight * b[token]
    norm_a = math.sqrt(sum(w * w for w in a.values()))
    norm_b = math.sqrt(sum(w * w for w in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def match_semantic(
    audit_docs: list[AuditDoc],
    issue_docs: list[IssueDoc],
    threshold: float,
) -> tuple[dict[str, dict], dict]:
    matches: dict[str, dict] = {}
    stage_counts = {"stage1": 0, "stage2": 0, "stage3": 0}

    all_docs_tokens = [doc.tokens for doc in audit_docs] + [doc.tokens for doc in issue_docs]
    idf = compute_idf(all_docs_tokens)
    issue_vecs = {doc.issue_id: tf_idf_vector(doc.tokens, idf) for doc in issue_docs}

    for item in audit_docs:
        item_vec = tf_idf_vector(item.tokens, idf)
        best_score = 0.0
        best_issue = None
        for issue in issue_docs:
            score = cosine_sim(item_vec, issue_vecs.get(issue.issue_id, {}))
            if score > best_score:
                best_score = score
                best_issue = issue.issue_id
        if best_issue and best_score >= threshold:
            matches[item.item_id] = {
                "stage": "stage2",
                "issue_id": best_issue,
                "score": best_score,
            }
            stage_counts["stage2"] += 1

    return matches, stage_counts


def evaluate_branches(
    branches: list[str],
    csv_path: Path,
    results_dir: Path,
    audit_classifications: set[str] | None,
    client_filter: str,
    client_keywords: list[str],
    threshold: float,
) -> None:
    issues = load_csv_issues(csv_path)

    summary = {
        "dataset": {"path": str(csv_path), "issues": len(issues)},
        "branches": {},
        "match_config": {"method": "tfidf_cosine", "threshold": threshold},
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

        issue_docs = build_issue_docs(filtered_issues)
        overall_issue_candidates.update(doc.issue_id for doc in issue_docs)

        files = sorted((results_dir / sanitized).glob("03_*.json"))
        audit_docs = extract_audit_docs(files, audit_classifications)

        matches, stage_counts = match_semantic(audit_docs, issue_docs, threshold)
        total = len(audit_docs)
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
    parser = argparse.ArgumentParser(description="Approximate semantic evaluation (TF-IDF cosine)")
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
    parser.add_argument(
        "--client-filter",
        type=str,
        default="auto",
        choices=["none", "auto", "keywords"],
    )
    parser.add_argument("--client-keywords", type=str, default="")
    parser.add_argument("--similarity-threshold", type=float, default=0.15)
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
        client_filter=client_filter,
        client_keywords=client_keywords,
        threshold=args.similarity_threshold,
    )


if __name__ == "__main__":
    main()
