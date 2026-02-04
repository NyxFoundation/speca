#!/usr/bin/env python3
"""Run security-agent benchmark runner (command-template driven)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from benchmarks.bench_utils import (
    extract_code,
    extract_id,
    guess_extension,
    iter_jsonl,
    sanitize_filename,
    write_jsonl,
)
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
DEFAULT_TMP = ROOT_DIR / "benchmarks" / "tmp" / "security_agent"
DEFAULT_METADATA = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run security-agent benchmark runner.")
    add_common_args(parser)
    parser.set_defaults(
        dataset=DEFAULT_DATASET,
        tmp_dir=DEFAULT_TMP,
        tool_name="security_agent",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.dataset.exists():
        print(f"Dataset not found: {args.dataset}", file=sys.stderr)
        return 1

    if args.output is None:
        args.output = default_results_path("security_agent", args.dataset)
    if args.metadata is None:
        args.metadata = default_metadata_path("security_agent", args.dataset)
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
            results.append(
                {
                    "id": case_id,
                    "predicted_vulnerable": None,
                    "error": "runner_not_configured",
                }
            )

    write_jsonl(spec.output, results)
    write_metadata(spec)
    print(f"Wrote {len(results)} security-agent results to {spec.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
