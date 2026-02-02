#!/usr/bin/env python3
"""
Run a single worker for parallel processing.

This script handles the iteration loop for a single worker, reading from its
assigned queue file and writing partial outputs with worker-specific naming.

Usage:
    python3 scripts/run_worker.py --phase 01b --worker-id 0 --max-iterations 100
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Phase configuration
PHASE_CONFIG = {
    "01b": {
        "queue_file": "outputs/01b_QUEUE_{worker_id}.json",
        "prompt_file": "prompts/01b_extract_worker.md",
        "log_prefix": "outputs/logs/01b_extract_w{worker_id}",
        "workdir": None,
    },
    "01c": {
        "queue_file": "outputs/01c_QUEUE_{worker_id}.json",
        "prompt_file": "prompts/01c_verify_worker.md",
        "log_prefix": "outputs/logs/01c_verify_w{worker_id}",
        "workdir": None,
    },
    "01d": {
        "queue_file": "outputs/01d_QUEUE_{worker_id}.json",
        "prompt_file": "prompts/01d_trustmodel_worker.md",
        "log_prefix": "outputs/logs/01d_trustmodel_w{worker_id}",
        "workdir": None,
    },
    "01e": {
        "queue_file": "outputs/01e_QUEUE_{worker_id}.json",
        "prompt_file": "prompts/01e_prop_worker.md",
        "log_prefix": "outputs/logs/01e_prop_w{worker_id}",
        "workdir": None,
        "max_batch_bytes": 160 * 1024,
    },
    "02": {
        "queue_file": "outputs/02_QUEUE_{worker_id}.json",
        "prompt_file": "prompts/02_checklist_worker.md",
        "log_prefix": "outputs/logs/02_checklist_w{worker_id}",
        "workdir": None,
        "max_batch_bytes": 120 * 1024,
    },
    "03": {
        "queue_file": "outputs/03_QUEUE_{worker_id}.json",
        "prompt_file": "prompts/03_auditmap_worker.md",
        "log_prefix": "outputs/logs/03_auditmap_w{worker_id}",
        "workdir": "target_workspace",
        "max_batch_bytes": 120 * 1024,
        "dynamic_batch_size_keys": ["checklist_file", "subgraph_file"],
    },
    "04": {
        "queue_file": "outputs/04_QUEUE_{worker_id}.json",
        "prompt_file": "prompts/04_review_worker.md",
        "log_prefix": "outputs/logs/04_review_w{worker_id}",
        "workdir": "target_workspace",
        "max_batch_bytes": 120 * 1024,
    },
}


def load_json(path: str) -> dict[str, Any]:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


def save_json(path: str, data: dict[str, Any]) -> None:
    """Save data to JSON file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def get_remaining_count(queue_file: str) -> int:
    """Get count of remaining items in queue."""
    try:
        data = load_json(queue_file)
        items = data.get("items", [])
        processed = set(data.get("processed", []))
        if items and isinstance(items[0], dict) and "property_id" in items[0]:
            remaining = [item for item in items if item.get("property_id") not in processed]
            return len(remaining)
        if items and isinstance(items[0], dict) and "check_id" in items[0]:
            remaining = [item for item in items if item.get("check_id") not in processed]
            return len(remaining)
        return len(items) - len(processed)
    except FileNotFoundError:
        return 0


def get_dynamic_batch_size(queue_file: str, max_bytes: int, config: dict[str, Any]) -> int:
    """Compute a dynamic batch size based on cumulative file size."""
    data = load_json(queue_file)
    items = data.get("items", [])
    processed = set(data.get("processed", []))
    if items and isinstance(items[0], dict) and "property_id" in items[0]:
        remaining = [item for item in items if item.get("property_id") not in processed]
    elif items and isinstance(items[0], dict) and "check_id" in items[0]:
        remaining = [item for item in items if item.get("check_id") not in processed]
    else:
        remaining = [item for item in items if item not in processed]

    if not remaining:
        return 0

    batch_count = 0
    cumulative_size = 0
    seen_files: set[str] = set()
    size_keys = config.get("dynamic_batch_size_keys", ["source_file"])

    for item in remaining:
        paths: list[str] = []
        if isinstance(item, dict):
            for key in size_keys:
                path = item.get(key)
                if path:
                    paths.append(path)
        else:
            paths = [item]

        if not paths:
            continue

        size_add = 0
        item_paths: set[str] = set()
        for path in paths:
            if not path or path in item_paths or not os.path.exists(path):
                continue
            item_paths.add(path)
            if path in seen_files:
                continue
            size_add += os.path.getsize(path)

        if batch_count == 0:
            batch_count = 1
            if size_add > max_bytes:
                break
            cumulative_size = size_add
            seen_files.update(item_paths)
            continue

        if cumulative_size + size_add > max_bytes:
            break

        batch_count += 1
        cumulative_size += size_add
        seen_files.update(item_paths)

    return batch_count


def run_claude(
    prompt_file: str,
    log_file: str,
    workdir: str | None,
    env_vars: dict,
    worker_id: int,
    queue_file: str,
    batch_size: int | None,
) -> tuple[bool, float, str]:
    """Run Claude with the given prompt and return success, duration, cost."""
    # Read prompt and append arguments (like 01a_crawl.md style)
    with open(prompt_file) as f:
        prompt_content = f.read()

    # Append arguments to prompt (matching Usage: format in metadata)
    extra_args = f"WORKER_ID={worker_id} QUEUE_FILE={queue_file}"
    if batch_size is not None:
        extra_args += f" BATCH_SIZE={batch_size}"
    if "OUTPUT_FILE" in env_vars:
        extra_args += f" OUTPUT_FILE={env_vars['OUTPUT_FILE']}"
    if "ITERATION" in env_vars:
        extra_args += f" ITERATION={env_vars['ITERATION']}"
    if "TIMESTAMP" in env_vars:
        extra_args += f" TIMESTAMP={env_vars['TIMESTAMP']}"
    prompt_content = f"{prompt_content}\n\n{extra_args}"

    # Build the command
    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "--agent", "serena",
        "--output-format", "json",
        "-p", prompt_content,
    ]

    # Set environment
    env = os.environ.copy()
    env.update(env_vars)
    if batch_size is not None:
        env["BATCH_SIZE"] = str(batch_size)
    env["CLAUDE_CODE_PERMISSIONS"] = "bypassPermissions"
    env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = "100000"

    start_time = time.time()

    try:
        # Run Claude
        cwd = workdir if workdir else None
        with open(log_file, "w") as f:
            result = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            def _stream_output() -> None:
                if result.stdout is None:
                    return
                for line in result.stdout:
                    f.write(line)
                    f.flush()
                    print(line, end="")

            import threading

            stream_thread = threading.Thread(target=_stream_output, daemon=True)
            stream_thread.start()

            try:
                result.wait(timeout=3600)  # 1 hour timeout per iteration
            except subprocess.TimeoutExpired:
                result.terminate()
                try:
                    result.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    result.kill()
                return False, time.time() - start_time, "timeout"

            stream_thread.join(timeout=1)

        duration = time.time() - start_time

        # Extract cost from output
        cost = "0"
        try:
            with open(log_file) as logf:
                log_lines = logf.read().split("\n")
            for line in log_lines:
                if '"total_cost_usd"' in line:
                    import re
                    match = re.search(r'"total_cost_usd":\s*([\d.]+)', line)
                    if match:
                        cost = match.group(1)
                        break
        except Exception:
            pass

        return result.returncode == 0, duration, cost
    except Exception as e:
        print(f"Error running Claude: {e}", file=sys.stderr)
        return False, time.time() - start_time, "error"


def main():
    parser = argparse.ArgumentParser(
        description="Run a single worker for parallel processing"
    )
    parser.add_argument(
        "--phase",
        required=True,
        choices=list(PHASE_CONFIG.keys()),
        help="Phase to run (01b, 01c, 01d, 01e, 02, 03, 04)",
    )
    parser.add_argument(
        "--worker-id",
        type=int,
        required=True,
        help="Worker ID (0-based)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=100,
        help="Maximum iterations per worker (default: 100)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Max items to process per iteration (default: prompt-defined)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without executing",
    )
    args = parser.parse_args()

    config = PHASE_CONFIG[args.phase]
    queue_file = config["queue_file"].format(worker_id=args.worker_id)
    prompt_file = config["prompt_file"]
    log_prefix = config["log_prefix"].format(worker_id=args.worker_id)
    workdir = config["workdir"]

    print(f"Worker {args.worker_id} starting for phase {args.phase}")
    print(f"  Queue file: {queue_file}")
    print(f"  Prompt file: {prompt_file}")

    # Check if queue file exists
    if not os.path.exists(queue_file):
        print(f"Queue file not found: {queue_file}")
        sys.exit(1)

    # Check if prompt file exists
    if not os.path.exists(prompt_file):
        print(f"Prompt file not found: {prompt_file}")
        print(f"Please create worker-specific prompt: {prompt_file}")
        sys.exit(1)

    # Environment variables for the prompt
    env_vars = {
        "WORKER_ID": str(args.worker_id),
        "QUEUE_FILE": queue_file,
    }

    iteration = 0
    total_cost = 0.0

    while iteration < args.max_iterations:
        remaining = get_remaining_count(queue_file)

        if remaining == 0:
            print(f"Worker {args.worker_id}: Queue complete after {iteration} iterations")
            break

        iteration += 1
        print(f"Worker {args.worker_id}: Iteration {iteration}, {remaining} items remaining")

        if args.dry_run:
            print(f"  [DRY RUN] Would run Claude with {prompt_file}")
            continue

        timestamp = int(time.time())
        env_vars["ITERATION"] = str(iteration)
        env_vars["TIMESTAMP"] = str(timestamp)
        log_file = f"{log_prefix}_{timestamp}_{iteration}.json"
        if args.phase == "02":
            output_file = (
                f"outputs/02_CHECKLIST_PARTIAL_W{args.worker_id}_{timestamp}_{iteration}.json"
            )
            env_vars["OUTPUT_FILE"] = output_file
        if args.phase == "03":
            output_file = (
                f"outputs/03_AUDITMAP_PARTIAL_W{args.worker_id}_{timestamp}_{iteration}.json"
            )
            env_vars["OUTPUT_FILE"] = output_file
        batch_size = args.batch_size
        if batch_size is None and args.phase in ("01e", "02", "03"):
            max_bytes = config.get("max_batch_bytes", 160 * 1024)
            batch_size = get_dynamic_batch_size(queue_file, max_bytes, config)
            if batch_size > 0:
                print(f"  Dynamic batch size: {batch_size} (max {max_bytes} bytes)")
            else:
                print("  Dynamic batch size: 0 (no readable items; falling back to 1)")
                batch_size = 1
        success, duration, cost = run_claude(
            prompt_file,
            log_file,
            workdir,
            env_vars,
            args.worker_id,
            queue_file,
            batch_size,
        )

        if cost not in ("timeout", "error"):
            try:
                total_cost += float(cost)
            except ValueError:
                pass

        status = "OK" if success else "FAILED"
        print(f"  Iteration {iteration}: {status} ({duration:.1f}s, ${cost})")

        if not success:
            print(f"Worker {args.worker_id}: Failed at iteration {iteration}", file=sys.stderr)
            # Continue anyway - the queue state should be preserved

    print(f"Worker {args.worker_id}: Completed {iteration} iterations, total cost: ${total_cost:.4f}")


if __name__ == "__main__":
    main()
