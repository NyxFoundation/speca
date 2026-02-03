#!/usr/bin/env python3
"""Runner for Semgrep against benchmark datasets."""

import json
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "benchmarks" / "data"
RESULTS_DIR = ROOT_DIR / "benchmarks" / "results"

def run_semgrep_on_primevul():
    """Run Semgrep on the PrimeVul dataset."""
    print("--> Running Semgrep on PrimeVul...")
    dataset_path = DATA_DIR / "primevul" / "primevul_test_paired.jsonl"
    output_path = RESULTS_DIR / "primevul" / "semgrep_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    with open(dataset_path, "r") as f:
        for line in f:
            sample = json.loads(line)
            func_id = sample.get("func_hash")
            code = sample.get("func")

            # Create a temporary file to scan
            temp_file = Path(f"/tmp/{func_id}.c")
            temp_file.write_text(code)

            # Run Semgrep
            # Using a generic ruleset for broad coverage. This can be customized.
            process = subprocess.run(
                ["semgrep", "--config", "p/c-audit", "--json", str(temp_file)],
                capture_output=True,
                text=True,
            )
            
            semgrep_output = json.loads(process.stdout)
            results.append({
                "func_id": func_id,
                "semgrep_findings": semgrep_output.get("results", []),
            })

            temp_file.unlink()

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"    Semgrep results saved to {output_path}")

def main():
    """Main function to run all benchmarks."""
    run_semgrep_on_primevul()
    # Add other dataset runners here

if __name__ == "__main__":
    main()
