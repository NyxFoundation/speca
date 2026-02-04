#!/usr/bin/env python3
"""Run CodeQL benchmark runner (command-template driven)."""

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
DEFAULT_TMP = ROOT_DIR / "benchmarks" / "tmp" / "codeql"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CodeQL benchmark runner.")
    add_common_args(parser)
    parser.set_defaults(
        dataset=DEFAULT_DATASET,
        tmp_dir=DEFAULT_TMP,
        tool_name="codeql",
    )
    return parser.parse_args()


def codeql_language_for_extension(ext: str) -> str | None:
    ext = ext.lower()
    if ext in {"c", "h", "cpp", "cxx", "cc", "hpp", "hh"}:
        return "cpp"
    if ext in {"java"}:
        return "java"
    return None


def build_command_for_extension(ext: str, code_path: Path) -> str | None:
    ext = ext.lower()
    if ext in {"c", "h"}:
        return f"clang -c {shlex.quote(str(code_path))}"
    if ext in {"cpp", "cxx", "cc", "hpp", "hh"}:
        return f"clang++ -c {shlex.quote(str(code_path))}"
    if ext in {"java"}:
        return f"javac {shlex.quote(str(code_path))}"
    return None


def query_pack_for_language(language: str) -> str:
    if language == "cpp":
        return "codeql/cpp-queries"
    return "codeql/java-queries"


def parse_sarif_findings(sarif_path: Path) -> int:
    if not sarif_path.exists():
        return 0
    try:
        data = json.loads(sarif_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    runs = data.get("runs") if isinstance(data, dict) else None
    if not isinstance(runs, list):
        return 0
    total = 0
    for run in runs:
        results = run.get("results") if isinstance(run, dict) else None
        if isinstance(results, list):
            total += len(results)
    return total


def run_codeql_default(code_path: Path, output_path: Path, ext: str, tmp_root: Path, timeout: int) -> tuple[bool | None, int, str | None]:
    if shutil.which("codeql") is None:
        return None, 0, "codeql_not_found"

    language = codeql_language_for_extension(ext)
    if language is None:
        return None, 0, "unsupported_language"

    build_command = build_command_for_extension(ext, code_path)
    if build_command is None:
        return None, 0, "unsupported_language"

    db_dir = tmp_root / f"{code_path.stem}_codeql_db"
    sarif_path = tmp_root / f"{code_path.stem}_codeql.sarif"
    if db_dir.exists():
        shutil.rmtree(db_dir)
    db_dir.mkdir(parents=True, exist_ok=True)

    create_cmd = [
        "codeql",
        "database",
        "create",
        str(db_dir),
        "--language",
        language,
        "--source-root",
        str(code_path.parent),
        "--command",
        build_command,
        "--overwrite",
    ]
    try:
        subprocess.run(create_cmd, check=False, capture_output=True, text=True, timeout=timeout or None)
    except subprocess.TimeoutExpired:
        return None, 0, "timeout"

    analyze_cmd = [
        "codeql",
        "database",
        "analyze",
        str(db_dir),
        query_pack_for_language(language),
        "--format",
        "sarifv2.1.0",
        "--output",
        str(sarif_path),
    ]
    try:
        subprocess.run(analyze_cmd, check=False, capture_output=True, text=True, timeout=timeout or None)
    except subprocess.TimeoutExpired:
        return None, 0, "timeout"

    findings = parse_sarif_findings(sarif_path)
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
        args.output = default_results_path("codeql", args.dataset)
    if args.metadata is None:
        args.metadata = default_metadata_path("codeql", args.dataset)

    spec = command_spec_from_args(args)
    spec.tmp_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for idx, record in enumerate(iter_jsonl(spec.dataset)):
        if spec.limit and idx >= spec.limit:
            break

        case_id = extract_id(record, idx)
        code = extract_code(record)
        if not code:
            results.append({"id": case_id, "predicted_vulnerable": None, "error": "missing_code"})
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
            prediction, findings, error = run_codeql_default(
                code_path, output_path, ext, spec.tmp_dir, spec.timeout
            )
            if error:
                results.append({"id": case_id, "predicted_vulnerable": None, "error": error})
            else:
                row = {"id": case_id, "predicted_vulnerable": prediction, "findings": findings}
                results.append(row)

    write_jsonl(spec.output, results)
    write_metadata(spec)
    print(f"Wrote {len(results)} CodeQL results to {spec.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
