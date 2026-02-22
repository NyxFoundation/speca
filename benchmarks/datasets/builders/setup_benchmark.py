#!/usr/bin/env python3
"""Downloads and prepares benchmark datasets."""

import os
import shutil
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "benchmarks" / "data"
CACHE_DIR = Path.home() / ".cache" / "security-agent" / "benchmarks"

# Dataset configurations
DATASETS = {
    "primevul": {
        "url": "https://huggingface.co/datasets/colin/PrimeVul/resolve/main/primevul_test_paired.jsonl",
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
    cache_file = CACHE_DIR / name / target_file.name

    if target_file.exists():
        print(f"    Dataset already exists at {target_file}. Skipping download.")
        return
    if cache_file.exists():
        print(f"    Using cached dataset at {cache_file}.")
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache_file, target_file)
        return

    print(f"    Downloading from {config['url']}...")
    subprocess.run(
        ["curl", "-L", "-f", "-o", str(target_file), config["url"]],
        check=True,
        capture_output=True,
    )
    # Sanity check: reject suspiciously small files (likely error pages)
    if target_file.stat().st_size < 1024:
        content = target_file.read_text(errors="replace")[:200]
        target_file.unlink()
        raise RuntimeError(f"Download failed — server returned error: {content}")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target_file, cache_file)
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
