#!/usr/bin/env python3
"""Dataset registry and path resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    default_path: Path


def resolve_dataset_path(name: str, override: Path | None, data_dir: Path) -> Path:
    if override:
        return override
    if name in DATASET_REGISTRY:
        return DATASET_REGISTRY[name].default_path
    return data_dir / name / f"{name}_paired.jsonl"


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "benchmarks" / "data"

DATASET_REGISTRY: dict[str, DatasetSpec] = {
    "primevul": DatasetSpec(
        name="primevul",
        default_path=DATA_DIR / "primevul" / "primevul_test_paired.jsonl",
    ),
    "cvefixes": DatasetSpec(
        name="cvefixes",
        default_path=DATA_DIR / "cvefixes" / "cvefixes_subset_paired.jsonl",
    ),
    "vul4j": DatasetSpec(
        name="vul4j",
        default_path=DATA_DIR / "vul4j" / "vul4j_paired.jsonl",
    ),
}
