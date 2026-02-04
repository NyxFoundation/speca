#!/usr/bin/env python3
"""Run a generic static analysis baseline runner (command-template driven)."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from benchmarks.bench_utils import extract_code, extract_id, guess_extension, iter_jsonl, sanitize_filename, write_jsonl
from benchmarks.runners.base_runner import (
    add_common_args,
    command_spec_from_args,
    default_metadata_path,
    default_prediction_loader,
    default_results_path,
    run_command,
    write_metadata,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT_DIR / "benchmarks" / "data" / "primevul" / "primevul_test_paired.jsonl"
DEFAULT_TMP = ROOT_DIR / "benchmarks" / "tmp" / "static_baseline"
DEFAULT_METADATA = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run static baseline benchmark runner.")
    add_common_args(parser)
    parser.set_defaults(
        dataset=DEFAULT_DATASET,
        tmp_dir=DEFAULT_TMP,
        tool_name="static_baseline",
    )
    return parser.parse_args()


def infer_compile_command(ext: str, code_path: Path) -> str | None:
    ext = ext.lower()
    if ext in {"c", "h"}:
        return f"clang -c {shlex.quote(str(code_path))}"
    if ext in {"cpp", "cxx", "cc", "hpp", "hh"}:
        return f"clang++ -c {shlex.quote(str(code_path))}"
    return None


def run_infer_default(code_path: Path, output_path: Path, ext: str, tmp_root: Path, timeout: int) -> tuple[bool | None, int, str | None]:
    if shutil.which("infer") is None:
        return None, 0, "infer_not_found"

    compile_command = infer_compile_command(ext, code_path)
    if compile_command is None:
        return None, 0, "unsupported_language"

    work_dir = tmp_root / f"{code_path.stem}_infer"
    work_dir.mkdir(parents=True, exist_ok=True)
    infer_out = work_dir / "infer-out" / "report.json"

    cmd = f"infer run --quiet -- {compile_command}"
    try:
        subprocess.run(cmd, shell=True, cwd=work_dir, capture_output=True, text=True, timeout=timeout or None)
    except subprocess.TimeoutExpired:
        return None, 0, "timeout"

    if not infer_out.exists():
        return None, 0, "infer_report_missing"

    try:
        data = json.loads(infer_out.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = []

    findings = 0
    if isinstance(data, list):
        findings = len(data)
    elif isinstance(data, dict):
        issues = data.get("issues") or data.get("results") or []
        if isinstance(issues, list):
            findings = len(issues)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"predicted_vulnerable": findings > 0, "findings": findings}, indent=2),
        encoding="utf-8",
    )
    return findings > 0, findings, None


def main() -> int:
    args = parse_args()
    if not args.dataset.exists():
        print(f"Dataset not found: {args.dataset}", file=sys.stderr)
        return 1

    if args.output is None:
        args.output = default_results_path("static_baseline", args.dataset)
    if args.metadata is None:
        args.metadata = default_metadata_path("static_baseline", args.dataset)
    spec = command_spec_from_args(args)
    spec.tmp_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for idx, record in enumerate(iter_jsonl(spec.dataset)):
        if spec.limit and idx >= spec.limit:
            break

        case_id = extract_id(record, idx)
        code = extract_code(record)
        if not code:
            results.append(
                {
                    "id": case_id,
                    "predicted_vulnerable": None,
                    "error": "missing_code",
                }
            )
            continue

        ext = guess_extension(record)
        safe_id = sanitize_filename(case_id)
        code_path = spec.tmp_dir / f"{safe_id}.{ext}"
        code_path.write_text(code, encoding="utf-8", errors="ignore")

        output_path = spec.tmp_dir / f"{safe_id}.prediction.json"

        if spec.command:
            return_code, stderr = run_command(
                spec.command, code_path, output_path, case_id, spec.use_shell, spec.timeout
            )
            prediction, extras, error = default_prediction_loader(output_path)
            if error:
                results.append(
                    {
                        "id": case_id,
                        "predicted_vulnerable": None,
                        "error": error,
                        "exit_code": return_code,
                        "stderr": stderr,
                    }
                )
            else:
                row = {"id": case_id, "predicted_vulnerable": prediction, "exit_code": return_code}
                if extras:
                    row.update(extras)
                results.append(row)
        else:
            prediction, findings, error = run_infer_default(
                code_path, output_path, ext, spec.tmp_dir, spec.timeout
            )
            if error:
                results.append(
                    {
                        "id": case_id,
                        "predicted_vulnerable": None,
                        "error": error,
                    }
                )
            else:
                results.append(
                    {
                        "id": case_id,
                        "predicted_vulnerable": prediction,
                        "findings": findings,
                    }
                )

    write_jsonl(spec.output, results)
    write_metadata(spec)
    print(f"Wrote {len(results)} static baseline results to {spec.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
