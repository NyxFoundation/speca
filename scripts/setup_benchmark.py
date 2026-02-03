#!/usr/bin/env python3
"""Downloads and prepares benchmark datasets."""

import os
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "benchmarks" / "data"

# Dataset configurations
DATASETS = {
    "primevul": {
        "url": "https://huggingface.co/datasets/DLVulDet/PrimeVul/resolve/main/primevul_test_paired.jsonl",
        "output_dir": DATA_DIR / "primevul",
    },
    # Add other datasets like VulDetectBench here
}


def setup_dataset(name: str, config: dict) -> None:
    """Download and set up a single dataset."""
    print(f"--> Setting up {name}...")
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    target_file = output_dir / os.path.basename(config["url"])

    if target_file.exists():
        print(f"    Dataset already exists at {target_file}. Skipping download.")
        return

    print(f"    Downloading from {config['url']}...")
    subprocess.run(
        ["curl", "-L", "-o", str(target_file), config["url"]],
        check=True,
        capture_output=True,
    )
    print(f"    Successfully downloaded to {target_file}")


def main() -> None:
    """Main function to set up all datasets."""
    print("Initializing benchmark data directory...")
    DATA_DIR.mkdir(exist_ok=True)

    for name, config in DATASETS.items():
        setup_dataset(name, config)

    print("\nAll benchmark datasets are ready.")


if __name__ == "__main__":
    main()
