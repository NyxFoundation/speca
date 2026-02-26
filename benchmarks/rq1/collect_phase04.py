#!/usr/bin/env python3
"""RQ1 Step 3.5 — Collect Phase 04 verdicts and compare metrics.

Loads Phase 04 review outputs, classifies verdicts as survived/filtered,
and recomputes recall/precision/F1 after the FP filter pipeline.
No LLM calls — purely deterministic comparison.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

# Phase 04 verdicts that cause a finding to be filtered out
_FILTERED_VERDICTS = {"DISPUTED_FP", "Disputed"}

# Phase 04 verdicts that survive the filter
_SURVIVED_VERDICTS = {
    "CONFIRMED_VULNERABILITY",
    "CONFIRMED_POTENTIAL",
    "DOWNGRADED",
    "NEEDS_MANUAL_REVIEW",
    "PASS_THROUGH",
}


def _classify_verdict(verdict: str) -> str:
    """Classify a verdict as 'survived' or 'filtered'."""
    v = (verdict or "").strip()
    if v in _FILTERED_VERDICTS:
        return "filtered"
    # Explicit survived verdicts, empty/unknown all survive (conservative)
    return "survived"


# ---------------------------------------------------------------------------
# Load Phase 04 verdicts
# ---------------------------------------------------------------------------


def load_phase04_verdicts(
    results_dir: Path, branches: list[str],
) -> tuple[dict[str, dict], list[str], list[str]]:
    """Load Phase 04 reviewed_items from all branches.

    Returns:
        verdicts: {property_id: {review_verdict, classification, branch, ...}}
        branches_with_04: branch names that had 04_*.json files
        branches_without_04: branch names that had no 04_*.json files
    """
    verdicts: dict[str, dict] = {}
    branches_with_04: list[str] = []
    branches_without_04: list[str] = []
    for branch in branches:
        branch_dir = results_dir / branch
        if not branch_dir.is_dir():
            continue
        files = sorted(branch_dir.glob("04_*.json"))
        if not files:
            branches_without_04.append(branch)
            continue
        branches_with_04.append(branch)
        for fpath in files:
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                print(f"[phase04] warning: cannot read {fpath}: {exc}", file=sys.stderr)
                continue
            items = data.get("reviewed_items", [])
            for item in items:
                pid = item.get("property_id", "")
                if not pid:
                    continue
                verdict = item.get("review_verdict", "")
                verdicts[pid] = {
                    "review_verdict": verdict,
                    "classification": _classify_verdict(verdict),
                    "adjusted_severity": item.get("adjusted_severity", ""),
                    "reviewer_notes": item.get("reviewer_notes", ""),
                    "branch": branch,
                    "source_file": fpath.name,
                }
    return verdicts, branches_with_04, branches_without_04


def verdict_breakdown(
    verdicts: dict[str, dict],
    total_findings: int,
    branches_with_04: list[str],
    branches_without_04: list[str],
) -> dict:
    """Summarise verdict counts including unreviewed findings."""
    by_verdict: dict[str, int] = {}
    survived = 0
    filtered = 0
    for info in verdicts.values():
        v = info["review_verdict"] or "(empty)"
        by_verdict[v] = by_verdict.get(v, 0) + 1
        if info["classification"] == "filtered":
            filtered += 1
        else:
            survived += 1
    unreviewed = max(0, total_findings - len(verdicts))
    return {
        "total_findings": total_findings,
        "total_reviewed": len(verdicts),
        "unreviewed": unreviewed,
        "by_verdict": dict(sorted(by_verdict.items())),
        "survived": survived,
        "filtered": filtered,
        "survived_total": survived + unreviewed,
        "branches_with_04": branches_with_04,
        "branches_without_04": branches_without_04,
    }


# ---------------------------------------------------------------------------
# Update run_metadata.json with Phase 04 timing
# ---------------------------------------------------------------------------


def update_run_metadata(metadata_path: Path, collection_summary_path: Path) -> None:
    """Append Phase 04 timing data from collection summary into run_metadata."""
    if not metadata_path.exists():
        print("[phase04] warning: run_metadata.json not found, skipping metadata update")
        return
    if not collection_summary_path.exists():
        print("[phase04] warning: collection_summary_04.json not found, skipping metadata update")
        return

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        collection = json.loads(collection_summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[phase04] warning: cannot read metadata files: {exc}", file=sys.stderr)
        return

    # Index collection branches by sanitized name
    col_by_branch: dict[str, dict] = {}
    for entry in collection.get("branches", []):
        sanitized = entry.get("sanitized_branch") or entry.get("branch", "").replace("/", "__")
        col_by_branch[sanitized] = entry

    targets = metadata.get("targets", [])
    for target in targets:
        branch = target.get("branch", "")
        sanitized = branch.replace("/", "__")
        col_entry = col_by_branch.get(sanitized, {})
        phase_logs = col_entry.get("phase_log_timing") or {}
        if phase_logs:
            target["phase_04"] = phase_logs

    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"[phase04] updated run_metadata.json with Phase 04 timing for {len(targets)} targets")


# ---------------------------------------------------------------------------
# Compare Phase 03 vs Phase 04 metrics
# ---------------------------------------------------------------------------


def _load_evaluation_summary(results_dir: Path) -> dict:
    p = results_dir / "evaluation_summary.json"
    if not p.exists():
        print(f"[phase04] error: {p} not found — run steps 02/03 first", file=sys.stderr)
        sys.exit(1)
    return json.loads(p.read_text(encoding="utf-8"))


def _load_labels_csv(results_dir: Path) -> list[dict]:
    p = results_dir / "findings_labels.csv"
    if not p.exists():
        print(f"[phase04] error: {p} not found — run step 03-eval-fp first", file=sys.stderr)
        sys.exit(1)
    rows: list[dict] = []
    with p.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def _compute_precision_from_rows(rows: list[dict]) -> dict:
    """Replicate evaluate.compute_precision() logic on a subset of rows.

    Label semantics (same as evaluate.py):
      tp              — matched H/M/L issue → TP
      tp_info         — matched info issue → TP
      potential-info  — real issue, contest caveat → TP
      fixed           — real issue already fixed → TP
      partially_fixed — real issue partially fixed → TP
      fp_invalid      — matched invalid issue → FP
      unknown         — no match
    """
    total = len(rows)
    auto_tp = sum(1 for r in rows if r.get("auto_label") == "tp")
    auto_fp_invalid = sum(1 for r in rows if r.get("auto_label") == "fp_invalid")
    auto_tp_info = sum(1 for r in rows if r.get("auto_label") == "tp_info")
    auto_tp_other = sum(1 for r in rows if r.get("auto_label") in {"potential-info", "fixed", "partially_fixed"})
    auto_unknown = sum(1 for r in rows if r.get("auto_label") == "unknown")

    human_tp = sum(1 for r in rows if (r.get("human_label") or "").strip().lower() in ("tp", "true", "1", "yes"))
    human_fp = sum(1 for r in rows if (r.get("human_label") or "").strip().lower() in ("fp", "false", "0", "no"))
    human_unlabeled = auto_unknown - human_tp - human_fp

    auto_tp_total = auto_tp + auto_tp_info + auto_tp_other
    total_tp = auto_tp_total + human_tp

    auto_labeled = auto_tp_total + auto_fp_invalid
    precision_auto = total_tp / auto_labeled if auto_labeled else 0.0
    precision_conservative = total_tp / total if total else 0.0

    return {
        "total_findings": total,
        "auto_tp": auto_tp,
        "auto_fp_invalid": auto_fp_invalid,
        "auto_tp_info": auto_tp_info,
        "auto_tp_other": auto_tp_other,
        "auto_unknown": auto_unknown,
        "human_tp": human_tp,
        "human_fp": human_fp,
        "human_unlabeled": human_unlabeled,
        "precision_auto": round(precision_auto, 4),
        "precision_conservative": round(precision_conservative, 4),
        "total_tp": total_tp,
    }


def compare_metrics(
    results_dir: Path,
    verdicts: dict[str, dict],
) -> dict:
    """Compare Phase 03 baseline metrics with post-Phase-04-filter metrics."""
    summary = _load_evaluation_summary(results_dir)
    all_rows = _load_labels_csv(results_dir)

    # Phase 03 baseline from evaluation_summary.json
    phase03_recall = summary.get("recall", 0.0)
    phase03_precision = summary.get("precision", {})
    phase03_f1 = summary.get("f1", 0.0)
    phase03_total = phase03_precision.get("total_findings", len(all_rows))
    recall_matches = summary.get("matches", {})  # {issue_id: {finding_id, confidence}}

    # Filtered property_ids
    filtered_pids = {pid for pid, info in verdicts.items() if info["classification"] == "filtered"}

    # --- Post-filter findings ---
    surviving_rows = [r for r in all_rows if r.get("finding_id") not in filtered_pids]

    # --- Post-filter recall ---
    # Check which recalled issues still have at least one surviving finding
    issues_total = summary.get("issues_total", 0)
    lost_recall_issues: list[str] = []
    surviving_matches: dict[str, dict] = {}
    for issue_id, match_info in recall_matches.items():
        fid = match_info.get("finding_id", "")
        if fid not in filtered_pids:
            surviving_matches[issue_id] = match_info
        else:
            lost_recall_issues.append(issue_id)

    phase04_recall = round(len(surviving_matches) / issues_total, 4) if issues_total else 0.0

    # --- Post-filter precision ---
    phase04_precision = _compute_precision_from_rows(surviving_rows)

    # --- Post-filter F1 ---
    p = phase04_precision["precision_auto"]
    r = phase04_recall
    phase04_f1 = round(2 * p * r / (p + r), 4) if (p > 0 and r > 0) else 0.0

    # --- Deltas ---
    p03_auto = phase03_precision.get("precision_auto", 0.0)

    comparison = {
        "phase_03": {
            "total_findings": phase03_total,
            "recall": phase03_recall,
            "precision_auto": p03_auto,
            "precision_conservative": phase03_precision.get("precision_conservative", 0.0),
            "f1": phase03_f1,
        },
        "phase_04": {
            "total_findings": phase04_precision["total_findings"],
            "recall": phase04_recall,
            "precision_auto": phase04_precision["precision_auto"],
            "precision_conservative": phase04_precision["precision_conservative"],
            "f1": phase04_f1,
            "lost_recall_issues": lost_recall_issues,
        },
        "delta": {
            "findings_removed": phase03_total - phase04_precision["total_findings"],
            "recall_delta": round(phase04_recall - phase03_recall, 4),
            "precision_auto_delta": round(phase04_precision["precision_auto"] - p03_auto, 4),
            "f1_delta": round(phase04_f1 - phase03_f1, 4),
        },
    }
    return comparison


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(results_dir: Path, collection_summary_path: Path | None = None) -> dict:
    """Entry point: load verdicts, update metadata, compare metrics."""
    # Discover branches from results dir
    branches = sorted(
        d.name for d in results_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )
    if not branches:
        print("[phase04] error: no branch directories found", file=sys.stderr)
        sys.exit(1)
    print(f"[phase04] branches: {', '.join(branches)}")

    # 1. Load verdicts
    verdicts, branches_with_04, branches_without_04 = load_phase04_verdicts(results_dir, branches)

    # Count total Phase 03 findings across all branches for unreviewed tracking
    total_findings = 0
    for branch in branches:
        branch_dir = results_dir / branch
        if not branch_dir.is_dir():
            continue
        for fpath in sorted(branch_dir.glob("03_*.json")):
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            items = data.get("audit_items", [])
            total_findings += len(items)

    breakdown = verdict_breakdown(verdicts, total_findings, branches_with_04, branches_without_04)
    print(
        f"[phase04] {breakdown['total_reviewed']} reviewed / {breakdown['unreviewed']} unreviewed (as-is) / "
        f"{breakdown['total_findings']} total findings"
    )
    print(
        f"[phase04] reviewed: {breakdown['survived']} survived, {breakdown['filtered']} filtered → "
        f"survived_total (reviewed + unreviewed): {breakdown['survived_total']}"
    )
    if branches_without_04:
        print(f"[phase04] branches without Phase 04: {', '.join(branches_without_04)}")
    if breakdown["total_reviewed"] == 0:
        print("[phase04] warning: 0 reviewed items — Phase 04 data may not be collected yet")

    # 2. Update run_metadata.json
    metadata_path = results_dir / "run_metadata.json"
    if collection_summary_path:
        update_run_metadata(metadata_path, collection_summary_path)

    # 3. Compare metrics
    comparison = compare_metrics(results_dir, verdicts)

    # 4. Write phase_comparison.json
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict_breakdown": breakdown,
        "verdicts": verdicts,
        "comparison": comparison,
    }
    out_path = results_dir / "phase_comparison.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    # Summary
    d = comparison["delta"]
    print(f"[phase04] Phase 03 → 04: findings {comparison['phase_03']['total_findings']} → {comparison['phase_04']['total_findings']} ({d['findings_removed']} removed)")
    print(f"[phase04] recall: {comparison['phase_03']['recall']:.1%} → {comparison['phase_04']['recall']:.1%} (delta {d['recall_delta']:+.4f})")
    print(f"[phase04] precision_auto: {comparison['phase_03']['precision_auto']:.1%} → {comparison['phase_04']['precision_auto']:.1%} (delta {d['precision_auto_delta']:+.4f})")
    print(f"[phase04] f1: {comparison['phase_03']['f1']:.3f} → {comparison['phase_04']['f1']:.3f} (delta {d['f1_delta']:+.4f})")
    if comparison["phase_04"]["lost_recall_issues"]:
        print(f"[phase04] lost recall issues: {comparison['phase_04']['lost_recall_issues']}")

    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="RQ1 Step 3.5: Collect Phase 04 verdicts and compare metrics")
    parser.add_argument(
        "--results-dir",
        default=str(ROOT_DIR / "benchmarks" / "results" / "rq1" / "sherlock_ethereum_audit_contest"),
        help="Results directory containing branch subdirs",
    )
    parser.add_argument(
        "--collection-summary",
        default="",
        help="Path to collection_summary_04.json (from --merge collection)",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    collection_summary = Path(args.collection_summary) if args.collection_summary else None
    run(results_dir, collection_summary)


if __name__ == "__main__":
    main()
