#!/usr/bin/env python3
"""RQ1 evaluation — recall + precision measurement.

Recall  = (H/M/L issues detected by audit) / (total H/M/L issues in CSV).
Precision = (true positive findings) / (total findings flagged as vuln).
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.rq1.matchers import (
    AuditItem,
    Issue,
    _truncate,
    check_findings_fp,
    extract_audit_items,
    load_csv_issues,
    match_issues,
    reparse_cache,
    reparse_fp_cache,
)


def parse_branches(value: str) -> list[str]:
    return [p.strip() for p in value.split(",") if p.strip()]


def sanitize_branch(branch: str) -> str:
    return branch.replace("/", "__")


def _load_all_findings(
    branches: list[str],
    results_dir: Path,
    audit_classifications: set[str] | None,
) -> list[AuditItem]:
    all_items: list[AuditItem] = []
    for branch in branches:
        sanitized = sanitize_branch(branch)
        files = sorted((results_dir / sanitized).glob("03_*.json"))
        items = extract_audit_items(files, classification_filter=audit_classifications, branch=branch)
        all_items.extend(items)
        print(f"[rq1] {branch}: {len(items)} findings")
    print(f"[rq1] total findings: {len(all_items)}")
    return all_items


def _run_recall(
    csv_path: Path,
    severity_filter: set[str],
    all_items: list[AuditItem],
    results_dir: Path,
    reparse: bool,
) -> tuple[dict[str, dict], int, list[Issue]]:
    issues = load_csv_issues(csv_path, severity_filter=severity_filter)
    print(f"[rq1] {len(issues)} H/M/L issues")

    cache_path = results_dir / "llm_cache.jsonl"
    if reparse and cache_path.exists():
        matches, llm_calls = reparse_cache(cache_path)
    else:
        matches, llm_calls = match_issues(issues, all_items, cache_path)

    return matches, llm_calls, issues


def _invert_recall_matches(recall_matches: dict[str, dict]) -> dict[str, list[str]]:
    """Invert {issue_id: {finding_id}} → {finding_id: [issue_ids]}."""
    tp_by_finding: dict[str, list[str]] = {}
    for issue_id, info in recall_matches.items():
        fid = info.get("finding_id")
        if fid:
            tp_by_finding.setdefault(fid, []).append(issue_id)
    return tp_by_finding


# ── Label CSV generation ─────────────────────────────────────────────


def _load_target_info(results_dir: Path) -> dict[str, dict]:
    """Load TARGET_INFO.json per branch → {branch: {repo, commit}}."""
    info: dict[str, dict] = {}
    for sub in sorted(results_dir.iterdir()):
        ti = sub / "TARGET_INFO.json"
        if sub.is_dir() and ti.exists():
            try:
                data = json.loads(ti.read_text(encoding="utf-8"))
                commit = str(data.get("target_commit") or "")
                info[sub.name] = {
                    "repo": str(data.get("target_repo") or ""),
                    "commit": commit[:10] if commit else "",
                }
            except (json.JSONDecodeError, OSError):
                pass
    return info


def generate_labels_csv(
    all_items: list[AuditItem],
    recall_matches: dict[str, dict],
    csv_path: Path,
    results_dir: Path,
    reparse: bool,
) -> Path:
    """Generate findings_labels.csv with auto_label for each finding."""
    tp_by_finding = _invert_recall_matches(recall_matches)
    tp_finding_ids = set(tp_by_finding.keys())

    # Unmatched findings need FP check
    unmatched = [f for f in all_items if f.item_id not in tp_finding_ids]
    print(f"[rq1] {len(tp_finding_ids)} TP findings, {len(unmatched)} to check for FP")

    # Load ALL CSV issues (no severity filter) for FP detection
    all_issues = load_csv_issues(csv_path)
    non_hml = [i for i in all_issues if i.severity not in ("high", "medium", "low")]
    print(f"[rq1] {len(non_hml)} non-H/M/L issues for FP check (invalid={sum(1 for i in non_hml if i.severity == 'invalid')}, info={sum(1 for i in non_hml if i.severity == 'info')})")

    fp_cache = results_dir / "llm_cache_fp.jsonl"
    if reparse and fp_cache.exists():
        fp_matches = reparse_fp_cache(fp_cache)
    else:
        fp_matches = check_findings_fp(unmatched, non_hml, cache_path=fp_cache)

    # Build issue lookup + target info
    issue_map = {i.issue_id: i for i in all_issues}
    target_info = _load_target_info(results_dir)

    # Write CSV
    out_path = results_dir / "findings_labels.csv"
    rows: list[dict] = []
    for item in all_items:
        branch_info = target_info.get(sanitize_branch(item.branch), {})
        row: dict[str, str] = {
            "finding_id": item.item_id,
            "repo": branch_info.get("repo", ""),
            "commit": branch_info.get("commit", ""),
            "classification": item.classification or "",
            "text": _truncate(item.text, 200),
            "auto_label": "",
            "csv_issue_id": "",
            "csv_severity": "",
            "csv_title": "",
            "human_label": "",
        }
        if item.item_id in tp_finding_ids:
            issue_ids = tp_by_finding[item.item_id]
            issue = issue_map.get(issue_ids[0])
            row["auto_label"] = "tp"
            row["csv_issue_id"] = issue_ids[0]
            row["csv_severity"] = issue.severity if issue else ""
            row["csv_title"] = issue.title if issue else ""
        elif item.item_id in fp_matches:
            fp = fp_matches[item.item_id]
            issue = issue_map.get(fp["issue_id"])
            severity = issue.severity if issue else fp.get("severity", "")
            row["auto_label"] = f"tp_{severity}" if severity == "info" else f"fp_{severity}" if severity else "fp"
            row["csv_issue_id"] = fp["issue_id"]
            row["csv_severity"] = severity
            row["csv_title"] = issue.title if issue else fp.get("title", "")
        else:
            row["auto_label"] = "unknown"
        rows.append(row)

    fieldnames = ["finding_id", "repo", "commit", "classification", "text", "auto_label",
                  "csv_issue_id", "csv_severity", "csv_title", "human_label"]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    labels = [r["auto_label"] for r in rows]
    print(f"[rq1] labels CSV: {out_path}")
    print(f"[rq1]   tp={labels.count('tp')} tp_info={labels.count('tp_info')} fp_invalid={labels.count('fp_invalid')} unknown={labels.count('unknown')}")
    return out_path


# ── Precision from labels CSV ────────────────────────────────────────


def compute_precision(labels_csv_path: Path) -> dict:
    """Compute precision metrics from findings_labels.csv."""
    rows: list[dict] = []
    with labels_csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    total = len(rows)
    auto_tp = sum(1 for r in rows if r.get("auto_label") == "tp")
    auto_fp_invalid = sum(1 for r in rows if r.get("auto_label") == "fp_invalid")
    auto_tp_info = sum(1 for r in rows if r.get("auto_label") == "tp_info")
    auto_unknown = sum(1 for r in rows if r.get("auto_label") == "unknown")

    # Human labels (if filled in)
    human_tp = sum(1 for r in rows if (r.get("human_label") or "").strip().lower() in ("tp", "true", "1", "yes"))
    human_fp = sum(1 for r in rows if (r.get("human_label") or "").strip().lower() in ("fp", "false", "0", "no"))
    human_unlabeled = total - auto_tp - auto_fp_invalid - auto_tp_info - human_tp - human_fp

    # tp_info = info-level finding (real issue, low severity) → counts as TP
    auto_tp_total = auto_tp + auto_tp_info

    # Precision calculations
    auto_labeled = auto_tp_total + auto_fp_invalid
    precision_auto = auto_tp_total / auto_labeled if auto_labeled else 0.0

    all_labeled = auto_labeled + human_tp + human_fp
    total_tp = auto_tp_total + human_tp
    precision_full = total_tp / all_labeled if all_labeled else 0.0

    # Conservative (treat unknown as FP)
    precision_conservative = total_tp / total if total else 0.0

    return {
        "total_findings": total,
        "auto_tp": auto_tp,
        "auto_fp_invalid": auto_fp_invalid,
        "auto_tp_info": auto_tp_info,
        "auto_unknown": auto_unknown,
        "human_tp": human_tp,
        "human_fp": human_fp,
        "human_unlabeled": human_unlabeled,
        "precision_auto": round(precision_auto, 4),
        "precision_full": round(precision_full, 4),
        "precision_conservative": round(precision_conservative, 4),
        "total_tp": total_tp,
    }


# ── Phase 04 verdict integration ────────────────────────────────────


_REJECT_VERDICTS = {"DISPUTED_FP"}
_ACCEPT_VERDICTS = {"CONFIRMED_VULNERABILITY", "CONFIRMED_POTENTIAL", "DOWNGRADED"}
_TP_LABELS = {"tp", "tp_info", "fixed", "partially_fixed"}
_FP_LABELS = {"fp_invalid"}


def _load_phase04_verdicts(partials_dir: Path) -> dict[str, str]:
    """Load Phase 04 PARTIAL files → {property_id: verdict}."""
    verdicts: dict[str, str] = {}
    for path in sorted(partials_dir.glob("04_PARTIAL_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for item in data.get("reviewed_items", []):
            pid = item.get("property_id", "")
            if pid:
                verdicts[pid] = item.get("review_verdict", "")
    return verdicts


def compute_phase04_impact(
    labels_csv_path: Path,
    phase04_verdicts: dict[str, str],
    recall_matches: dict[str, dict],
) -> dict:
    """Compute Phase 04 impact on precision/recall vs Phase 03 baseline.

    Returns metrics showing how Phase 04 filtering changes FP/FN rates.
    """
    rows: list[dict] = []
    with labels_csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    total = len(rows)
    processed = 0
    # Confusion matrix counts
    p04_tp = 0   # Phase 04 accepted a real finding
    p04_fn = 0   # Phase 04 rejected a real finding (false negative)
    p04_tn = 0   # Phase 04 rejected an FP (correct)
    p04_fp = 0   # Phase 04 accepted an FP (false positive retained)

    fn_details: list[dict] = []

    for row in rows:
        fid = row["finding_id"]
        auto_label = row.get("auto_label", "")

        if fid not in phase04_verdicts:
            continue
        processed += 1
        verdict = phase04_verdicts[fid]

        if verdict in _ACCEPT_VERDICTS and auto_label in _TP_LABELS:
            p04_tp += 1
        elif verdict in _REJECT_VERDICTS and auto_label in _TP_LABELS:
            p04_fn += 1
            fn_details.append({
                "finding_id": fid,
                "benchmark_label": auto_label,
                "csv_severity": row.get("csv_severity", ""),
                "csv_issue_id": row.get("csv_issue_id", ""),
            })
        elif verdict in _REJECT_VERDICTS and auto_label in _FP_LABELS:
            p04_tn += 1
        elif verdict in _ACCEPT_VERDICTS and auto_label in _FP_LABELS:
            p04_fp += 1

    # Impact on recall: which Sherlock issues are lost due to Phase 04 FNs?
    fn_finding_ids = {d["finding_id"] for d in fn_details}
    recall_issues_lost: list[str] = []
    for issue_id, match_info in recall_matches.items():
        if match_info.get("finding_id") in fn_finding_ids:
            recall_issues_lost.append(issue_id)

    return {
        "phase04_processed": processed,
        "phase04_unprocessed": total - processed,
        "confusion": {
            "true_positive": p04_tp,
            "false_negative": p04_fn,
            "true_negative": p04_tn,
            "false_positive_retained": p04_fp,
        },
        "false_negatives": fn_details,
        "recall_issues_lost": recall_issues_lost,
    }


# ── Main evaluation ─────────────────────────────────────────────────


def evaluate(
    branches: list[str],
    csv_path: Path,
    results_dir: Path,
    severity_filter: set[str],
    audit_classifications: set[str] | None,
    metadata_path: Path | None = None,
    reparse: bool = False,
    label: bool = False,
) -> dict:
    all_items = _load_all_findings(branches, results_dir, audit_classifications)
    recall_matches, llm_calls, issues = _run_recall(
        csv_path, severity_filter, all_items, results_dir, reparse,
    )

    # Severity breakdown
    severity_breakdown = {}
    for sev in sorted(severity_filter):
        sev_issues = [i for i in issues if i.severity == sev]
        sev_matched = sum(1 for i in sev_issues if i.issue_id in recall_matches)
        severity_breakdown[sev] = {
            "total": len(sev_issues),
            "matched": sev_matched,
            "recall": round(sev_matched / len(sev_issues), 4) if sev_issues else 0.0,
        }

    recall = round(len(recall_matches) / len(issues), 4) if issues else 0.0

    summary: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {"path": str(csv_path), "issues_csv_total": len(load_csv_issues(csv_path))},
        "severity_filter": sorted(severity_filter),
        "audit_classifications": sorted(audit_classifications) if audit_classifications else None,
        "branches": [sanitize_branch(b) for b in branches],
        "audit_items_total": len(all_items),
        "issues_total": len(issues),
        "issues_matched": len(recall_matches),
        "recall": recall,
        "severity_breakdown": severity_breakdown,
        "llm_calls": llm_calls,
        "matches": recall_matches,
        "missed_issues": [
            {
                "issue_id": i.issue_id,
                "severity": i.severity,
                "title": i.title,
            }
            for i in issues
            if i.issue_id not in recall_matches
        ],
    }

    # Generate labels CSV (FP detection)
    if label:
        generate_labels_csv(all_items, recall_matches, csv_path, results_dir, reparse)

    # Compute precision if labels CSV exists
    labels_csv = results_dir / "findings_labels.csv"
    if labels_csv.exists():
        prec = compute_precision(labels_csv)
        summary["precision"] = prec
        # F1
        if prec["precision_full"] > 0 and recall > 0:
            summary["f1"] = round(2 * prec["precision_full"] * recall / (prec["precision_full"] + recall), 4)
        else:
            summary["f1"] = 0.0
        print(f"[rq1] precision={prec['precision_full']:.1%} f1={summary['f1']:.3f}")

    # Phase 04 impact (if Phase 04 outputs exist)
    phase04_verdicts = _load_phase04_verdicts(results_dir.parent.parent.parent / "outputs")
    if not phase04_verdicts:
        # Also try the results_dir parent chain for different layouts
        for candidate in [results_dir / ".." / ".." / ".." / "outputs", Path("outputs")]:
            candidate = candidate.resolve()
            if candidate.is_dir():
                phase04_verdicts = _load_phase04_verdicts(candidate)
                if phase04_verdicts:
                    break

    if phase04_verdicts and labels_csv.exists():
        p04_impact = compute_phase04_impact(labels_csv, phase04_verdicts, recall_matches)
        summary["phase04_impact"] = p04_impact
        p04_proc = p04_impact["phase04_processed"]
        cm = p04_impact["confusion"]
        print(f"[rq1] phase04: {p04_proc} processed, fn={cm['false_negative']}, tn={cm['true_negative']}")
        if p04_impact["recall_issues_lost"]:
            print(f"[rq1] phase04 recall issues lost: {p04_impact['recall_issues_lost']}")

    if metadata_path and metadata_path.exists():
        try:
            summary["run_metadata"] = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary["run_metadata"] = {"error": "invalid_json"}

    summary_path = results_dir / "evaluation_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[rq1] recall: {len(recall_matches)}/{len(issues)} = {recall:.1%}")
    return summary
