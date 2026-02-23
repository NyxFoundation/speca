#!/usr/bin/env python3
"""Common runner helpers for benchmark tools."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CommandSpec:
    dataset: Path
    output: Path
    tmp_dir: Path
    command: str
    version_command: str
    timeout: int
    use_shell: bool
    limit: int
    tool_name: str
    metadata: Path


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=False, default=None)
    parser.add_argument("--tmp-dir", type=Path, default=None)
    parser.add_argument("--metadata", type=Path, required=False, default=None)
    parser.add_argument("--tool-name", type=str, default="")
    parser.add_argument(
        "--command",
        default="",
        help="Command template: {code_path} {output_path} {case_id}",
    )
    parser.add_argument("--version-command", default="", help="Command to get tool version")
    parser.add_argument("--timeout", type=int, default=0)
    parser.add_argument("--shell", action="store_true")
    parser.add_argument("--limit", type=int, default=0)


def command_spec_from_args(args: argparse.Namespace) -> CommandSpec:
    return CommandSpec(
        dataset=args.dataset,
        output=args.output,
        tmp_dir=args.tmp_dir,
        command=args.command,
        version_command=args.version_command,
        timeout=args.timeout,
        use_shell=args.shell,
        limit=args.limit,
        tool_name=args.tool_name,
        metadata=args.metadata,
    )


def default_results_path(tool_name: str, dataset_path: Path) -> Path:
    dataset_name = dataset_path.parent.name
    return ROOT_DIR / "benchmarks" / "results" / "rq2" / dataset_name / f"{tool_name}_results.jsonl"


def default_metadata_path(tool_name: str, dataset_path: Path) -> Path:
    dataset_name = dataset_path.parent.name
    return ROOT_DIR / "benchmarks" / "results" / "rq2" / dataset_name / f"{tool_name}_metadata.json"


def run_command(
    template: str, code_path: Path, output_path: Path, case_id: str, use_shell: bool, timeout: int
) -> tuple[int, str]:
    if use_shell:
        formatted = template.format(
            code_path=shlex.quote(str(code_path)),
            output_path=shlex.quote(str(output_path)),
            case_id=shlex.quote(case_id),
        )
    else:
        formatted = template.format(code_path=code_path, output_path=output_path, case_id=case_id)
    try:
        if use_shell:
            result = subprocess.run(formatted, shell=True, capture_output=True, text=True, timeout=timeout or None)
        else:
            result = subprocess.run(shlex.split(formatted), capture_output=True, text=True, timeout=timeout or None)
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    return result.returncode, result.stderr.strip()


def resolve_version(command: str) -> str | None:
    if not command:
        return None
    try:
        result = subprocess.run(shlex.split(command), capture_output=True, text=True)
    except Exception:
        return None
    output = (result.stdout or result.stderr).strip()
    return output or None


def write_metadata(spec: CommandSpec, extra: dict | None = None) -> None:
    metadata = {
        "tool": spec.tool_name,
        "dataset": str(spec.dataset),
        "output": str(spec.output),
        "command": spec.command,
        "version": resolve_version(spec.version_command),
        "timeout_sec": spec.timeout,
        "limit": spec.limit,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        metadata.update(extra)
    spec.metadata.parent.mkdir(parents=True, exist_ok=True)
    spec.metadata.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


PredictionLoader = Callable[[Path], tuple[bool | None, dict | None, str | None]]


def default_prediction_loader(path: Path) -> tuple[bool | None, dict | None, str | None]:
    if not path.exists():
        return None, None, "missing_prediction_output"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, None, "prediction_json_parse_failed"
    prediction = data.get("predicted_vulnerable")
    if isinstance(prediction, bool):
        normalized = prediction
    elif isinstance(prediction, (int, float)):
        normalized = bool(prediction)
    elif isinstance(prediction, str):
        lowered = prediction.strip().lower()
        if lowered in {"true", "1", "yes", "vulnerable"}:
            normalized = True
        elif lowered in {"false", "0", "no", "clean", "non-vulnerable"}:
            normalized = False
        else:
            return None, None, "prediction_missing_or_invalid"
    else:
        return None, None, "prediction_missing_or_invalid"
    extras = {}
    if "confidence" in data and isinstance(data["confidence"], (int, float)):
        extras["confidence"] = max(0.0, min(1.0, float(data["confidence"])))
    if "findings" in data and isinstance(data["findings"], (int, float)):
        extras["findings"] = data["findings"]
    return normalized, extras, None
