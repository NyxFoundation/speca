#!/usr/bin/env python3
"""RQ1 evaluation orchestration and aggregation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
import random
from pathlib import Path

from benchmarks.bench_utils import normalize_bool
from benchmarks.rq1.matchers import AuditItem, Issue, extract_audit_items, load_csv_issues, match_items
from benchmarks.metrics.stats import bootstrap_rate, effect_size_cliffs_delta, mcnemar_exact


def parse_branches(value: str) -> list[str]:
    parts = [item.strip() for item in value.split(",")]
    return [p for p in parts if p]


def sanitize_branch(branch: str) -> str:
    return branch.replace("/", "__")


def extract_human_label(record: dict) -> bool | None:
    for key in (
        "label",
        "is_valid_bug",
        "is_bug",
        "is_true_positive",
        "valid",
        "bug",
        "verdict",
    ):
        if key in record:
            value = normalize_bool(record.get(key))
            if value is not None:
                return value
    return None


def match_branch(
    branch: str,
    issues: list[Issue],
    results_dir: Path,
    use_llm: bool,
    llm_max: int,
    stage1_threshold: float,
    stage2_threshold: float,
    keyword_min_overlap: int,
    candidate_top_k: int,
) -> tuple[dict, list[AuditItem]]:
    sanitized = sanitize_branch(branch)
    branch_dir = results_dir / sanitized
    files = sorted(branch_dir.glob("03_*.json"))
    audit_items = extract_audit_items(files)

    matches, stage_counts, llm_calls = match_items(
        audit_items,
        issues,
        use_llm,
        llm_max,
        stage1_threshold,
        stage2_threshold,
        keyword_min_overlap,
        candidate_top_k,
    )

    total = len(audit_items)
    matched_total = len(matches)
    new_total = total - matched_total
    overlap_rate = matched_total / total if total else 0.0
    new_rate = new_total / total if total else 0.0
    matched_issue_ids = {match["issue_id"] for match in matches.values() if match.get("issue_id")}
    issues_matched_total = len(matched_issue_ids)
    issue_recall = issues_matched_total / len(issues) if issues else 0.0

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
        "llm_used": use_llm,
        "llm_calls": llm_calls,
        "matches": matches,
    }

    detail_path = results_dir / f"evaluation_{sanitized}.json"
    detail_path.write_text(json.dumps(detail, indent=2), encoding="utf-8")
    return detail, audit_items


def evaluate_branches(
    branches: list[str],
    csv_path: Path,
    results_dir: Path,
    use_llm: bool,
    llm_max: int,
    stage1_threshold: float,
    stage2_threshold: float,
    keyword_min_overlap: int,
    candidate_top_k: int,
    baseline_dir: Path | None,
    bootstrap_samples: int,
    bootstrap_seed: int,
    ci_level: float,
    human_scope: str,
    human_sample_size: int,
    human_sample_out: Path | None,
    human_labels: Path | None,
    human_labels_report: Path | None,
    metadata_path: Path | None,
) -> dict:
    issues = load_csv_issues(csv_path)
    issue_map = {issue.issue_id: issue for issue in issues}

    summary = {
        "dataset": {"path": str(csv_path), "issues": len(issues)},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "branches": {},
        "match_config": {
            "stage1_threshold": stage1_threshold,
            "stage2_threshold": stage2_threshold,
            "keyword_min_overlap": keyword_min_overlap,
            "candidate_top_k": candidate_top_k,
            "llm_max": llm_max,
            "llm_used": use_llm,
        },
    }
    if metadata_path and metadata_path.exists():
        try:
            summary["run_metadata"] = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary["run_metadata"] = {"error": "invalid_json", "path": str(metadata_path)}

    human_candidates: list[dict] = []
    human_lookup: dict[tuple[str, str], dict] = {}

    overall_matched_issue_ids: set[str] = set()

    for branch in branches:
        detail, audit_items = match_branch(
            branch,
            issues,
            results_dir,
            use_llm,
            llm_max,
            stage1_threshold,
            stage2_threshold,
            keyword_min_overlap,
            candidate_top_k,
        )

        matched_flags = [item.item_id in detail["matches"] for item in audit_items]
        overlap_ci = bootstrap_rate(matched_flags, samples=bootstrap_samples, seed=bootstrap_seed, ci_level=ci_level)
        new_ci = bootstrap_rate(
            [not flag for flag in matched_flags],
            samples=bootstrap_samples,
            seed=bootstrap_seed,
            ci_level=ci_level,
        )

        baseline_stats = {}
        if baseline_dir:
            baseline_path = baseline_dir / f"evaluation_{detail['sanitized_branch']}.json"
            if baseline_path.exists():
                baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
                baseline_matches = baseline.get("matches", {})
                b = c = 0
                n = 0
                for item in audit_items:
                    current_matched = item.item_id in detail["matches"]
                    baseline_matched = item.item_id in baseline_matches
                    n += 1
                    if current_matched and not baseline_matched:
                        b += 1
                    elif not current_matched and baseline_matched:
                        c += 1
                p_value = mcnemar_exact(b, c)
                delta, magnitude = effect_size_cliffs_delta(b, c, n)
                baseline_stats = {
                    "baseline_path": str(baseline_path),
                    "n": n,
                    "discordant": {"current_only_matched": b, "baseline_only_matched": c},
                    "mcnemar_p": p_value,
                    "effect_size": {"cliffs_delta": delta, "magnitude": magnitude},
                }

        summary["branches"][branch] = {
            "items_total": detail["items_total"],
            "matched_total": detail["matched_total"],
            "new_total": detail["new_total"],
            "overlap_rate": detail["overlap_rate"],
            "new_rate": detail["new_rate"],
            "issues_matched_total": detail["issues_matched_total"],
            "issue_recall": detail["issue_recall"],
            "overlap_rate_ci": overlap_ci,
            "new_rate_ci": new_ci,
            "stage_counts": detail["stage_counts"],
            "llm_used": detail["llm_used"],
            "llm_calls": detail["llm_calls"],
        }
        if baseline_stats:
            summary["branches"][branch]["baseline_comparison"] = baseline_stats

        overall_matched_issue_ids.update(
            match["issue_id"] for match in detail["matches"].values() if match.get("issue_id")
        )

        for item in audit_items:
            matched = item.item_id in detail["matches"]
            if human_scope == "new_only" and matched:
                continue
            issue_id = detail["matches"].get(item.item_id, {}).get("issue_id")
            issue = issue_map.get(issue_id) if issue_id else None
            record = {
                "branch": branch,
                "item_id": item.item_id,
                "matched": matched,
                "stage": detail["matches"].get(item.item_id, {}).get("stage") if matched else None,
                "issue_id": issue_id,
                "issue_title": issue.title if issue else None,
                "issue_description": issue.description if issue else None,
                "description": item.description,
                "snippet": item.snippet,
                "file": item.file,
                "line": item.line,
                "text": item.text,
            }
            human_candidates.append(record)
            human_lookup[(branch, item.item_id)] = record

    summary["issues_matched_total"] = len(overall_matched_issue_ids)
    summary["issue_recall"] = len(overall_matched_issue_ids) / len(issues) if issues else 0.0

    summary_path = results_dir / "evaluation_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if human_sample_size > 0 and human_candidates:
        rng = random.Random(bootstrap_seed)
        sample_size = min(human_sample_size, len(human_candidates))
        sampled = rng.sample(human_candidates, k=sample_size)
        out_path = human_sample_out or results_dir / "human_eval_sample.jsonl"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as handle:
            for record in sampled:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    if human_labels and human_labels.exists():
        labeled = 0
        positives = 0
        labels = []
        invalid = []
        for line in human_labels.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                invalid.append({"reason": "invalid_json"})
                continue
            branch = record.get("branch")
            item_id = record.get("item_id")
            if not branch or not item_id:
                invalid.append({"reason": "missing_branch_or_item_id", "record": record})
                continue
            label = extract_human_label(record)
            if label is None:
                invalid.append({"reason": "missing_or_invalid_label", "record": record})
                continue
            if (branch, item_id) not in human_lookup:
                invalid.append({"reason": "unknown_item_id", "record": record})
                continue
            labeled += 1
            if label:
                positives += 1
            labels.append(label)
        human_stats = {
            "scope": human_scope,
            "labeled_total": labeled,
            "true_bug": positives,
            "precision": positives / labeled if labeled else 0.0,
            "precision_ci": bootstrap_rate(labels, bootstrap_samples, bootstrap_seed, ci_level),
            "bootstrap": {
                "samples": bootstrap_samples,
                "ci_level": ci_level,
                "seed": bootstrap_seed,
            },
            "invalid_label_rows": len(invalid),
        }
        summary["human_eval"] = human_stats
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if human_labels_report:
            report_path = human_labels_report
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report = {
                "labels_path": str(human_labels),
                "invalid_count": len(invalid),
                "invalid_samples": invalid[:50],
            }
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return summary
