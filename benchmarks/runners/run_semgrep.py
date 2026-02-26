#!/usr/bin/env python3
"""Runner for Semgrep against benchmark datasets."""

import argparse
import json
import logging
import subprocess
from pathlib import Path

from benchmarks.bench_utils import extract_id, guess_extension
from benchmarks.runners.base_runner import CommandSpec, write_metadata

logger = logging.getLogger(__name__)

CODE_KEYS = ["func", "before", "after", "code"]

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "benchmarks" / "data"
RESULTS_DIR = ROOT_DIR / "benchmarks" / "results"


def default_output_path(dataset_path: Path) -> Path:
    dataset_name = dataset_path.parent.name
    return RESULTS_DIR / "rq2" / dataset_name / "semgrep_results.json"


def default_metadata_path(dataset_path: Path) -> Path:
    dataset_name = dataset_path.parent.name
    return RESULTS_DIR / "rq2" / dataset_name / "semgrep_metadata.json"

def run_semgrep_on_primevul(dataset_path: Path, output_path: Path, config: str, timeout: int = 0):
    """Run Semgrep on the dataset."""
    print(f"--> Running Semgrep on {dataset_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    with open(dataset_path, "r") as f:
        for idx, line in enumerate(f):
            sample = json.loads(line)
            func_id = extract_id(sample, idx)

            # BUG-BEN08: Try multiple code keys for CVEfixes compat
            code = None
            for key in CODE_KEYS:
                code = sample.get(key)
                if code is not None:
                    break

            # BUG-BEN05: Skip samples with no code
            if code is None:
                logger.warning("Sample %s has no code (tried keys: %s), skipping", func_id, CODE_KEYS)
                results.append({
                    "func_id": func_id,
                    "semgrep_findings": [],
                    "error": "missing_code",
                })
                continue

            # BUG-BEN04: Use correct extension based on language
            ext = guess_extension(sample)
            temp_file = Path(f"/tmp/{func_id}.{ext}")
            temp_file.write_text(code)

            # Run Semgrep
            try:
                process = subprocess.run(
                    ["semgrep", "--config", config, "--json", str(temp_file)],
                    capture_output=True,
                    text=True,
                    timeout=timeout or None,
                )
            except subprocess.TimeoutExpired:
                results.append({
                    "func_id": func_id,
                    "semgrep_findings": [],
                    "error": "timeout",
                })
                temp_file.unlink()
                continue
            
            # BUG-BEN06: Handle non-JSON output from Semgrep gracefully
            try:
                semgrep_output = json.loads(process.stdout) if process.stdout else {}
            except json.JSONDecodeError:
                results.append({
                    "func_id": func_id,
                    "semgrep_findings": [],
                    "error": "semgrep_json_parse_failed",
                    "raw_output": (process.stdout or "")[:500],
                })
                temp_file.unlink(missing_ok=True)
                continue
            results.append({
                "func_id": func_id,
                "semgrep_findings": semgrep_output.get("results", []),
            })

            temp_file.unlink()

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    
    metadata_path = default_metadata_path(dataset_path)
    write_metadata(
        CommandSpec(
            dataset=dataset_path,
            output=output_path,
            tmp_dir=Path("/tmp"),
            command=f"semgrep --config {config}",
            version_command="semgrep --version",
            timeout=timeout,
            use_shell=False,
            limit=0,
            tool_name="semgrep",
            metadata=metadata_path,
        ),
        extra={"config": config},
    )
    print(f"    Semgrep results saved to {output_path}")

def main():
    """Main function to run all benchmarks."""
    parser = argparse.ArgumentParser(description="Run Semgrep benchmark runner.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DATA_DIR / "primevul" / "primevul_test_paired.jsonl",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--config", type=str, default="auto")
    parser.add_argument("--timeout", type=int, default=0, help="Per-sample timeout in seconds (0 = no timeout)")
    args = parser.parse_args()
    output_path = args.output or default_output_path(args.dataset)
    run_semgrep_on_primevul(args.dataset, output_path, args.config, timeout=args.timeout)
    # Add other dataset runners here

if __name__ == "__main__":
    main()
