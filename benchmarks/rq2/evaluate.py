#!/usr/bin/env python3
"""Evaluates and compares the results of different tools."""

from __future__ import annotations

import json
import re
import argparse
from collections import Counter, defaultdict
import os
from pathlib import Path
from typing import Iterable

from benchmarks.bench_utils import extract_code, extract_id, extract_label, guess_extension, normalize_bool
from benchmarks.datasets.registry import resolve_dataset_path
from benchmarks.metrics.classification import compute_confusion
from benchmarks.metrics.stats import bootstrap_metric_diffs, effect_size_cliffs_delta, mcnemar_exact
from benchmarks.tools.registry import TOOL_REGISTRY, resolve_metadata_path, resolve_results_path

ROOT_DIR = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT_DIR / "benchmarks" / "results" / "rq2"
DATA_DIR = ROOT_DIR / "benchmarks" / "data"
EVALUATION_OUTPUT_PATH = RESULTS_DIR / "evaluation_summary.json"
METRICS_OUTPUT_PATH = RESULTS_DIR / "metrics.json"

CWE_KEYS = ("cwe_id", "cwe", "cwe_ids", "cwes", "cwe_id_list", "cwe_list")
PAIR_KEYS = ("pair_id", "pair", "pair_hash", "pair_idx", "pair_index", "pair_uuid", "pair_key", "pair_group")
CVE_KEYS = ("cve", "cve_id", "cveid", "cveId")
PATH_KEYS = ("file", "file_path", "path", "filename")
SPEC_KEYS = ("spec", "specification", "requirements", "rationale", "evidence", "explanation", "reasoning")

EXAMPLE_LIMIT = 5
SNIPPET_MAX_LINES = 14
SNIPPET_MAX_CHARS = 900
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_SEED = 42
CI_LEVEL = 0.95


def load_jsonl(path: Path) -> list[dict]:
    """Load a .jsonl file."""
    data: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            data.append(json.loads(line))
    return data


def first_value(record: dict, keys: Iterable[str]) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_ground_truth(record: dict) -> bool | None:
    if "vul_type" in record:
        value = record.get("vul_type")
        if isinstance(value, str):
            return value.strip().lower() != "clean"
        normalized = normalize_bool(value)
        if normalized is not None:
            return normalized
    return extract_label(record)


def normalize_cwe(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (int, float)):
        return [f"CWE-{int(value)}"]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        matches = re.findall(r"CWE-?\d+", text, flags=re.IGNORECASE)
        if matches:
            return [match.upper().replace("CWE", "CWE-").replace("CWE--", "CWE-") for match in matches]
        if text.isdigit():
            return [f"CWE-{int(text)}"]
        return [text]
    if isinstance(value, (list, tuple, set)):
        normalized: list[str] = []
        for item in value:
            normalized.extend(normalize_cwe(item))
        return normalized
    return []


def extract_cwes(record: dict) -> list[str]:
    for key in CWE_KEYS:
        if key in record:
            cwes = normalize_cwe(record.get(key))
            if cwes:
                return cwes
    return ["unknown"]


def extract_pair_id(record: dict) -> str | None:
    for key in PAIR_KEYS:
        value = record.get(key)
        if value is not None and value != "":
            return str(value)
    return None






def build_code_snippet(code: str | None) -> str | None:
    if not code:
        return None
    lines = code.strip().splitlines()
    snippet_lines = lines[:SNIPPET_MAX_LINES]
    snippet = "\n".join(snippet_lines)
    if len(lines) > SNIPPET_MAX_LINES or len(snippet) > SNIPPET_MAX_CHARS:
        snippet = snippet[:SNIPPET_MAX_CHARS].rstrip() + "\n... (truncated)"
    return snippet


def extract_spec_evidence(extra: dict) -> str | None:
    for key in SPEC_KEYS:
        value = extra.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def count_by_cwe(case_ids: Iterable[str], cwe_map: dict[str, list[str]]) -> Counter:
    counts: Counter = Counter()
    for case_id in case_ids:
        for cwe in cwe_map.get(case_id, ["unknown"]):
            counts[cwe] += 1
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate benchmark results.")
    parser.add_argument("--dataset", type=str, default="primevul")
    parser.add_argument("--dataset-path", type=Path, default=None)
    return parser.parse_args()


def evaluate_dataset(dataset_name: str, dataset_path: Path) -> dict:
    """Evaluate tool performance on a paired dataset."""
    print(f"--> Evaluating results for {dataset_name}...")
    if not dataset_path.exists():
        print(f"    Dataset not found: {dataset_path}")
        return {
            "dataset": {"name": dataset_name, "path": str(dataset_path), "ground_truth_count": 0},
            "tools": {},
            "comparisons": {},
        }

    ground_truth: dict[str, bool | None] = {}
    cwe_map: dict[str, list[str]] = {}
    record_map: dict[str, dict] = {}
    pair_map: dict[str, list[str]] = defaultdict(list)

    for idx, record in enumerate(load_jsonl(dataset_path)):
        case_id = extract_id(record, idx)
        record_map[case_id] = record
        ground_truth[case_id] = extract_ground_truth(record)
        cwe_map[case_id] = extract_cwes(record)
        pair_id = extract_pair_id(record)
        if pair_id:
            pair_map[pair_id].append(case_id)

    total_cwe_counts = Counter()
    for case_id, label in ground_truth.items():
        if label:
            for cwe in cwe_map.get(case_id, ["unknown"]):
                total_cwe_counts[cwe] += 1

    tools_payload: dict[str, dict] = {}
    predictions_by_tool: dict[str, dict[str, bool | None]] = {}
    extras_by_tool: dict[str, dict[str, dict]] = {}

    tool_sources = {
        name: (resolve_results_path(spec, dataset_name, RESULTS_DIR), spec.loader)
        for name, spec in TOOL_REGISTRY.items()
    }

    for tool, (path, loader) in tool_sources.items():
        if path is None:
            tools_payload[tool] = {"status": "missing_results"}
            predictions_by_tool[tool] = {}
            extras_by_tool[tool] = {}
            continue
        loaded = loader(path)
        if loaded is None:
            tools_payload[tool] = {"status": "invalid_results", "results_path": str(path)}
            predictions_by_tool[tool] = {}
            extras_by_tool[tool] = {}
            continue
        predictions, error_count, extras = loaded
        predictions_by_tool[tool] = predictions
        extras_by_tool[tool] = extras
        metrics = compute_confusion(predictions, ground_truth)
        metrics["status"] = "ok"
        metrics["results_path"] = str(path)
        metrics["error_count"] = error_count
        tools_payload[tool] = metrics

    # Pairwise correctness
    eligible_pairs: list[tuple[str, str, str]] = []
    pair_skipped = 0
    for pair_id, case_ids in pair_map.items():
        if len(case_ids) != 2:
            pair_skipped += 1
            continue
        labels = [ground_truth.get(case_id) for case_id in case_ids]
        if None in labels:
            pair_skipped += 1
            continue
        if labels.count(True) != 1 or labels.count(False) != 1:
            pair_skipped += 1
            continue
        vuln_id = case_ids[labels.index(True)]
        clean_id = case_ids[labels.index(False)]
        eligible_pairs.append((pair_id, vuln_id, clean_id))

    for tool, predictions in predictions_by_tool.items():
        if tools_payload.get(tool, {}).get("status") != "ok":
            continue
        correct = 0
        skipped = 0
        for _, vuln_id, clean_id in eligible_pairs:
            vuln_pred = predictions.get(vuln_id)
            clean_pred = predictions.get(clean_id)
            if vuln_pred is None or clean_pred is None:
                skipped += 1
                continue
            if vuln_pred is True and clean_pred is False:
                correct += 1
        total = len(eligible_pairs)
        scored = total - skipped
        accuracy = correct / scored if scored else 0.0
        tools_payload[tool]["pairwise"] = {
            "correct": correct,
            "scored": scored,
            "total": total,
            "skipped": skipped,
            "accuracy": accuracy,
        }

    # CWE coverage and missed CWE counts
    for tool, predictions in predictions_by_tool.items():
        if tools_payload.get(tool, {}).get("status") != "ok":
            continue
        tp_ids = [case_id for case_id, label in ground_truth.items() if label and predictions.get(case_id) is True]
        missed_ids = [case_id for case_id, label in ground_truth.items() if label and predictions.get(case_id) is not True]
        tp_by_cwe = count_by_cwe(tp_ids, cwe_map)
        missed_by_cwe = count_by_cwe(missed_ids, cwe_map)
        coverage = {}
        for cwe, total in total_cwe_counts.items():
            tp = tp_by_cwe.get(cwe, 0)
            coverage[cwe] = {"tp": tp, "total": total, "recall": tp / total if total else 0.0}
        tools_payload[tool]["cwe_coverage"] = coverage
        tools_payload[tool]["missed_by_cwe"] = dict(missed_by_cwe)

    # Unique detections for security-agent
    comparisons: dict[str, dict] = {}
    if tools_payload.get("security_agent", {}).get("status") == "ok":
        baseline_tools = [
            tool for tool in predictions_by_tool if tool != "security_agent" and tools_payload.get(tool, {}).get("status") == "ok"
        ]
        unique_ids: list[str] = []
        for case_id, label in ground_truth.items():
            if not label:
                continue
            if predictions_by_tool["security_agent"].get(case_id) is True and all(
                predictions_by_tool[tool].get(case_id) is not True for tool in baseline_tools
            ):
                unique_ids.append(case_id)

        unique_by_cwe = {}
        for case_id in unique_ids:
            for cwe in cwe_map.get(case_id, ["unknown"]):
                unique_by_cwe.setdefault(cwe, []).append(case_id)

        examples = []
        for case_id in unique_ids[:EXAMPLE_LIMIT]:
            record = record_map.get(case_id, {})
            extra = extras_by_tool.get("security_agent", {}).get(case_id, {})
            code_snippet = build_code_snippet(extract_code(record))
            example = {
                "id": case_id,
                "cwe": cwe_map.get(case_id, ["unknown"]),
                "cve": first_value(record, CVE_KEYS),
                "path": first_value(record, PATH_KEYS),
                "language": record.get("language") or guess_extension(record),
                "code_snippet": code_snippet,
                "spec_evidence": extract_spec_evidence(extra),
            }
            examples.append(example)

        comparisons["unique_detections"] = {
            "security_agent_only": {
                "count": len(unique_ids),
                "ids": unique_ids,
                "by_cwe": {cwe: {"count": len(ids), "ids": ids} for cwe, ids in unique_by_cwe.items()},
                "examples": examples,
                "compared_against": baseline_tools,
            }
        }
    else:
        comparisons["unique_detections"] = {"security_agent_only": {"count": 0, "ids": [], "by_cwe": {}, "examples": []}}

    # Pairwise statistics (security_agent vs baselines)
    pairwise_stats: dict[str, dict] = {}
    if tools_payload.get("security_agent", {}).get("status") == "ok":
        for tool in predictions_by_tool:
            if tool == "security_agent":
                continue
            if tools_payload.get(tool, {}).get("status") != "ok":
                continue
            eligible_cases = [
                case_id
                for case_id, label in ground_truth.items()
                if label is not None
                and predictions_by_tool["security_agent"].get(case_id) is not None
                and predictions_by_tool[tool].get(case_id) is not None
            ]
            b = c = 0
            for case_id in eligible_cases:
                label = ground_truth[case_id]
                a_pred = predictions_by_tool["security_agent"][case_id]
                b_pred = predictions_by_tool[tool][case_id]
                a_correct = a_pred == label
                b_correct = b_pred == label
                if a_correct and not b_correct:
                    b += 1
                elif not a_correct and b_correct:
                    c += 1
            n = len(eligible_cases)
            p_value = mcnemar_exact(b, c)
            delta, magnitude = effect_size_cliffs_delta(b, c, n)
            diffs = bootstrap_metric_diffs(
                predictions_by_tool["security_agent"],
                predictions_by_tool[tool],
                ground_truth,
                eligible_cases,
            )
            pairwise_stats[tool] = {
                "n": n,
                "discordant": {"security_agent_only_correct": b, "baseline_only_correct": c},
                "mcnemar_p": p_value,
                "effect_size": {"cliffs_delta": delta, "magnitude": magnitude},
                "metric_diffs": diffs,
                "bootstrap": {
                    "samples": BOOTSTRAP_SAMPLES,
                    "ci_level": CI_LEVEL,
                    "seed": BOOTSTRAP_SEED,
                },
            }
    comparisons["pairwise_stats"] = pairwise_stats

    dataset_summary = {
        "name": dataset_name,
        "path": str(dataset_path),
        "ground_truth_count": len([v for v in ground_truth.values() if v is not None]),
        "sample_count": len(ground_truth),
        "pair_count": len(pair_map),
        "pair_eligible": len(eligible_pairs),
        "pair_skipped": pair_skipped,
        "cwe_totals": dict(total_cwe_counts),
    }

    tool_metadata = {}
    for tool, spec in TOOL_REGISTRY.items():
        meta_path = resolve_metadata_path(spec, dataset_name, RESULTS_DIR)
        if meta_path.exists():
            try:
                tool_metadata[tool] = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                tool_metadata[tool] = {"error": "invalid_json", "path": str(meta_path)}

    metrics = {
        "dataset": dataset_summary,
        "tools": tools_payload,
        "comparisons": comparisons,
        "tool_metadata": tool_metadata,
    }
    return metrics


def main() -> None:
    """Main evaluation function."""
    args = parse_args()
    dataset_path = resolve_dataset_path(args.dataset, args.dataset_path, DATA_DIR)
    metrics = evaluate_dataset(args.dataset, dataset_path)
    metadata_path = os.environ.get("BENCHMARK_METADATA_PATH", "")
    if metadata_path:
        path = Path(metadata_path)
        if path.exists():
            try:
                metrics["run_metadata"] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                metrics["run_metadata"] = {"error": "invalid_json", "path": str(path)}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with METRICS_OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)
    with EVALUATION_OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)
    print(f"    Evaluation summary saved to {EVALUATION_OUTPUT_PATH}")
    print(f"    Metrics saved to {METRICS_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
