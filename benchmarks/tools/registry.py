#!/usr/bin/env python3
"""Tool registry and path resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from benchmarks.tools.loaders import load_jsonl_predictions, load_semgrep_results

ToolLoader = Callable[[Path], tuple[dict[str, bool | None], int, dict[str, dict]] | None]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    patterns: tuple[str, ...]
    loader: ToolLoader
    metadata_filename: str


def pick_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def resolve_results_path(spec: ToolSpec, dataset_name: str, results_dir: Path) -> Path | None:
    dataset_paths = [results_dir / dataset_name / filename for filename in spec.patterns]
    root_paths = [results_dir / filename for filename in spec.patterns]
    return pick_existing(dataset_paths + root_paths)


def resolve_metadata_path(spec: ToolSpec, dataset_name: str, results_dir: Path) -> Path:
    return results_dir / dataset_name / spec.metadata_filename


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "semgrep": ToolSpec(
        name="semgrep",
        patterns=("semgrep_results.json", "semgrep.json"),
        loader=load_semgrep_results,
        metadata_filename="semgrep_metadata.json",
    ),
    "codeql": ToolSpec(
        name="codeql",
        patterns=("codeql_results.jsonl", "codeql.jsonl"),
        loader=load_jsonl_predictions,
        metadata_filename="codeql_metadata.json",
    ),
    "security_agent": ToolSpec(
        name="security_agent",
        patterns=("security_agent_results.jsonl", "security_agent.jsonl"),
        loader=load_jsonl_predictions,
        metadata_filename="security_agent_metadata.json",
    ),
    "llm_baseline": ToolSpec(
        name="llm_baseline",
        patterns=("llm_baseline_results.jsonl", "llm_baseline.jsonl"),
        loader=load_jsonl_predictions,
        metadata_filename="llm_baseline_metadata.json",
    ),
    "static_baseline": ToolSpec(
        name="static_baseline",
        patterns=("static_baseline_results.jsonl", "static_baseline.jsonl"),
        loader=load_jsonl_predictions,
        metadata_filename="static_baseline_metadata.json",
    ),
}
