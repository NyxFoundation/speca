#!/usr/bin/env python3
"""
Orchestrate parallel execution of multiple workers.

This script splits the queue, runs workers in parallel, and merges results.

Usage:
    python3 scripts/run_parallel.py --phase 01b --workers 4
    python3 scripts/run_parallel.py --phase 02b --workers 4 --max-iterations 50
"""

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def run_split(phase: str, workers: int) -> bool:
    """Run the split_queue.py script."""
    print(f"\n{'='*60}")
    print(f"Phase 1: Splitting queue for {workers} workers")
    print(f"{'='*60}")

    result = subprocess.run(
        ["python3", "scripts/split_queue.py", "--phase", phase, "--workers", str(workers)],
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return False

    return True


def run_workers_parallel(phase: str, workers: int, max_iterations: int, batch_size: int | None) -> bool:
    """Run all workers in parallel."""
    print(f"\n{'='*60}")
    print(f"Phase 2: Running {workers} workers in parallel")
    print(f"{'='*60}")

    start_time = time.time()
    processes: dict[int, subprocess.Popen[str]] = {}

    for worker_id in range(workers):
        cmd = [
            "python3", "scripts/run_worker.py",
            "--phase", phase,
            "--worker-id", str(worker_id),
            "--max-iterations", str(max_iterations),
        ]
        if batch_size is not None:
            cmd += ["--batch-size", str(batch_size)]
        print(f"Starting worker {worker_id}...")
        processes[worker_id] = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

    # Stream outputs in real time with a simple prefix
    import threading

    def stream_worker_output(wid: int, proc: subprocess.Popen[str]) -> None:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            print(f"[W{wid}] {line}", end="")

    threads = []
    for wid, proc in processes.items():
        t = threading.Thread(target=stream_worker_output, args=(wid, proc), daemon=True)
        t.start()
        threads.append(t)

    results: dict[int, bool] = {}
    for wid, proc in processes.items():
        code = proc.wait()
        results[wid] = code == 0
        status = "OK" if code == 0 else "FAILED"
        print(f"Worker {wid}: {status}")

    for t in threads:
        t.join(timeout=1)

    duration = time.time() - start_time
    print(f"\nAll workers completed in {duration:.1f}s")

    return all(results.values())


def run_merge(phase: str, output_file: str) -> bool:
    """Run the merge_results.py script."""
    print(f"\n{'='*60}")
    print(f"Phase 3: Merging results")
    print(f"{'='*60}")

    result = subprocess.run(
        ["python3", "scripts/merge_results.py", "--phase", phase, "--output", output_file],
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return False

    return True


# Output file mapping (None = no merge needed, partials are the output)
OUTPUT_FILES = {
    "01b": None,  # No merge - subgraphs are kept separate
    "01c": None,  # No merge - verified subgraphs
    "01d": None,  # No merge - trust model partials
    "01e": None,  # No merge - property partials
    "02a": None,  # No merge - checklist partials
    "02b": None,  # No merge - checklist partials
    "03": None,   # No merge - audit map partials
    "04": None,   # No merge - review partials
}


def main():
    parser = argparse.ArgumentParser(
        description="Orchestrate parallel execution of workers"
    )
    parser.add_argument(
        "--phase",
        required=True,
        choices=["01b", "01c", "01d", "01e", "02a", "02b", "03", "04"],
        help="Phase to run",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=100,
        help="Max iterations per worker (default: 100)",
    )
    parser.add_argument(
        "--skip-split",
        action="store_true",
        help="Skip queue splitting (use existing queue files)",
    )
    parser.add_argument(
        "--skip-merge",
        action="store_true",
        help="Skip result merging",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Max items to process per iteration (default: prompt-defined)",
    )
    parser.add_argument(
        "--output",
        help="Override output file for merge",
    )
    args = parser.parse_args()

    print(f"Parallel execution for phase {args.phase}")
    print(f"  Workers: {args.workers}")
    print(f"  Max iterations per worker: {args.max_iterations}")
    if args.batch_size is not None:
        print(f"  Batch size: {args.batch_size}")

    start_time = time.time()

    # Step 1: Split queue
    if not args.skip_split:
        if not run_split(args.phase, args.workers):
            print("ERROR: Queue splitting failed", file=sys.stderr)
            sys.exit(1)
    else:
        print("\nSkipping queue split (--skip-split)")

    # Step 2: Run workers in parallel
    if not run_workers_parallel(args.phase, args.workers, args.max_iterations, args.batch_size):
        print("WARNING: Some workers failed", file=sys.stderr)
        # Continue to merge anyway

    # Step 3: Merge results (if configured)
    output_file = args.output or OUTPUT_FILES.get(args.phase)
    if output_file and not args.skip_merge:
        if not run_merge(args.phase, output_file):
            print("ERROR: Result merging failed", file=sys.stderr)
            sys.exit(1)
    else:
        print("\nSkipping merge (no merge configured or --skip-merge)")

    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"Parallel execution complete in {total_time:.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
