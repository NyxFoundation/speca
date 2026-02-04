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
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Phase configuration
ROOT_DIR = Path(__file__).resolve().parents[1]
BUG_BOUNTY_SCOPE_PATH = ROOT_DIR / "outputs" / "BUG_BOUNTY_SCOPE.json"


def resolve_root_path(path: str) -> str:
    """Resolve a path relative to the repo root."""
    path_obj = Path(path)
    if path_obj.is_absolute():
        return str(path_obj)
    return str(ROOT_DIR / path_obj)


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
    """Save data to JSON file atomically."""
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=path_obj.name, dir=str(path_obj.parent))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path_obj)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def save_text(path: str, content: str) -> None:
    """Save text to file atomically."""
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=path_obj.name, dir=str(path_obj.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path_obj)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def extract_item_ids(items: list[Any]) -> list[str]:
    """Extract item IDs from a queue item list."""
    ids: list[str] = []
    for item in items:
        if isinstance(item, dict):
            if "check_id" in item:
                ids.append(item["check_id"])
            elif "property_id" in item:
                ids.append(item["property_id"])
        elif isinstance(item, str):
            ids.append(item)
    return [i for i in ids if i]


def extract_output_ids(output_data: Any, phase: str) -> list[str]:
    """Extract processed IDs from a phase output file."""
    if phase == "02":
        if isinstance(output_data, dict):
            checklist = output_data.get("checklist") or output_data.get("checklist_items") or []
        else:
            checklist = []
        # Phase 02 queue tracks property_id, not check_id
        return [
            item.get("property_id")
            for item in checklist
            if isinstance(item, dict) and item.get("property_id")
        ]
    if phase == "04":
        if isinstance(output_data, dict):
            reviewed_items = output_data.get("reviewed_items", [])
        else:
            reviewed_items = []
        ids: list[str] = []
        for item in reviewed_items:
            if not isinstance(item, dict):
                continue
            original_item = item.get("original_item", {})
            if isinstance(original_item, dict) and original_item.get("check_id"):
                ids.append(original_item["check_id"])
        return ids
    if phase in ("01d", "01e"):
        if isinstance(output_data, dict):
            metadata = output_data.get("metadata", {})
            source_files = metadata.get("source_files", []) if isinstance(metadata, dict) else []
            if isinstance(source_files, list):
                return [p for p in source_files if isinstance(p, str)]
    return []


def normalize_queue(queue_file: str, phase: str, output_file: str | None) -> bool:
    """Normalize queue/processed consistency based on items and output file."""
    try:
        queue_data = load_json(queue_file)
    except Exception as exc:
        print(f"Warning: Failed to load queue file for normalization: {exc}", file=sys.stderr)
        return False

    items = queue_data.get("items", [])
    items_ids = set(extract_item_ids(items))

    processed_list = queue_data.get("processed", [])
    if not isinstance(processed_list, list):
        processed_list = []
    processed_ids = set([p for p in processed_list if isinstance(p, str)])

    output_ids: set[str] = set()
    if output_file:
        try:
            output_data = load_json(output_file)
            output_ids = set(extract_output_ids(output_data, phase))
        except Exception as exc:
            print(f"Warning: Failed to parse output file for normalization: {exc}", file=sys.stderr)

    # Keep only IDs that exist in items; add only IDs that appeared in output.
    normalized = (processed_ids | output_ids) & items_ids
    queue_data["processed"] = sorted(normalized)

    save_json(queue_file, queue_data)
    return True


def validate_output_ids(output_file: str | None, phase: str) -> list[str]:
    """Return output IDs if output file is valid; empty list if invalid or missing."""
    if not output_file or not os.path.exists(output_file):
        return []
    try:
        output_data = load_json(output_file)
    except Exception:
        return []
    return extract_output_ids(output_data, phase)


def update_queue_with_ids(queue_file: str, new_ids: list[str]) -> None:
    """Update queue processed list with new IDs, constrained to items."""
    queue_data = load_json(queue_file)
    items = queue_data.get("items", [])
    items_ids = set(extract_item_ids(items))

    processed_list = queue_data.get("processed", [])
    if not isinstance(processed_list, list):
        processed_list = []
    processed_ids = set([p for p in processed_list if isinstance(p, str)])

    normalized = (processed_ids | set(new_ids)) & items_ids
    queue_data["processed"] = sorted(normalized)
    save_json(queue_file, queue_data)


def collect_01b_output_ids(worker_id: int, timestamp: int, iteration: int) -> list[str]:
    """Collect processed URLs from 01b output files created this iteration."""
    outputs_dir = ROOT_DIR / "outputs" / "01b_SUBGRAPHS"
    pattern = f"spec_*_{timestamp}_{iteration}.json"
    ids: list[str] = []
    for path in outputs_dir.glob(pattern):
        try:
            data = load_json(str(path))
        except Exception:
            continue
        if isinstance(data, dict):
            src = data.get("source_url")
            if isinstance(src, str) and src:
                ids.append(src)
    return ids


def collect_01c_output_ids(worker_id: int, timestamp: int, iteration: int) -> list[str]:
    """Collect processed file paths from 01c verified copies created this iteration."""
    outputs_dir = ROOT_DIR / "outputs" / "01b_SUBGRAPHS"
    pattern = f"spec_*_verified_{timestamp}_{iteration}.json"
    ids: list[str] = []
    for path in outputs_dir.glob(pattern):
        name = path.name
        if not name.startswith("spec_") or "_verified_" not in name:
            continue
        # spec_<hash>_verified_{timestamp}_{iteration}.json -> spec_<hash>.json
        original = name.split("_verified_")[0] + ".json"
        ids.append(str(outputs_dir / original))
    return ids


def load_bug_bounty_scope() -> dict[str, Any] | None:
    """Load Bug Bounty Scope from outputs/BUG_BOUNTY_SCOPE.json if present."""
    if not BUG_BOUNTY_SCOPE_PATH.exists():
        return None
    try:
        with open(BUG_BOUNTY_SCOPE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        print(f"Warning: Failed to parse {BUG_BOUNTY_SCOPE_PATH}: {exc}", file=sys.stderr)
        return None


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
            if not path:
                continue
            resolved_path = resolve_root_path(path)
            if resolved_path in item_paths or not os.path.exists(resolved_path):
                continue
            item_paths.add(resolved_path)
            if resolved_path in seen_files:
                continue
            size_add += os.path.getsize(resolved_path)

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
    bug_bounty_scope: dict[str, Any] | None,
) -> tuple[bool, float, str]:
    """Run Claude with the given prompt and return success, duration, cost."""
    # Read prompt and append arguments (like 01a_crawl.md style)
    with open(prompt_file) as f:
        prompt_content = f.read()

    if bug_bounty_scope:
        scope_json = json.dumps(bug_bounty_scope, indent=2, ensure_ascii=True)
        scope_block = (
            "# Bug Bounty Scope\n\n"
            "The following Bug Bounty Scope has been provided for this audit:\n\n"
            "```json\n"
            f"{scope_json}\n"
            "```\n\n"
            "Use this scope definition to determine which components are in-scope and out-of-scope.\n\n"
            "---\n\n"
        )
        prompt_content = f"{scope_block}{prompt_content}"

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
    if "AUDIT_SCOPE" in env_vars:
        extra_args += f" AUDIT_SCOPE={env_vars['AUDIT_SCOPE']}"
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
    Path(".claude/debug").mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(Path.cwd())

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
        help="Phase to run (01b, 01c, 01d, 01e, 02, 04)",
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
    queue_file = resolve_root_path(config["queue_file"].format(worker_id=args.worker_id))
    prompt_file = resolve_root_path(config["prompt_file"])
    log_prefix = resolve_root_path(config["log_prefix"].format(worker_id=args.worker_id))
    workdir = config["workdir"]
    if workdir:
        workdir = resolve_root_path(workdir)

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
    audit_scope = os.environ.get("AUDIT_SCOPE")
    if audit_scope and audit_scope != "auto":
        env_vars["AUDIT_SCOPE"] = audit_scope
    bug_bounty_scope = None
    if args.phase in ("01d", "01e", "02"):
        bug_bounty_scope = load_bug_bounty_scope()

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
            env_vars["OUTPUT_FILE"] = resolve_root_path(output_file)
        if args.phase == "01d":
            output_file = (
                f"outputs/01d_TRUSTMODEL_PARTIAL_W{args.worker_id}_{timestamp}_{iteration}.json"
            )
            env_vars["OUTPUT_FILE"] = resolve_root_path(output_file)
        if args.phase == "01e":
            output_file = (
                f"outputs/01e_PROP_PARTIAL_W{args.worker_id}_{timestamp}_{iteration}.json"
            )
            env_vars["OUTPUT_FILE"] = resolve_root_path(output_file)
        if args.phase == "04":
            output_file = (
                f"outputs/04_REVIEW_PARTIAL_W{args.worker_id}_{timestamp}_{iteration}.json"
            )
            env_vars["OUTPUT_FILE"] = resolve_root_path(output_file)
        batch_size = args.batch_size
        if batch_size is None and args.phase in ("01e", "02"):
            max_bytes = config.get("max_batch_bytes", 160 * 1024)
            batch_size = get_dynamic_batch_size(queue_file, max_bytes, config)
            if batch_size > 0:
                print(f"  Dynamic batch size: {batch_size} (max {max_bytes} bytes)")
            else:
                print("  Dynamic batch size: 0 (no readable items; falling back to 1)")
                batch_size = 1
        # Snapshot queue before running Claude so we can restore on failure/invalid output.
        try:
            queue_snapshot = Path(queue_file).read_text()
        except Exception:
            queue_snapshot = ""

        success, duration, cost = run_claude(
            prompt_file,
            log_file,
            workdir,
            env_vars,
            args.worker_id,
            queue_file,
            batch_size,
            bug_bounty_scope,
        )

        if cost not in ("timeout", "error"):
            try:
                total_cost += float(cost)
            except ValueError:
                pass

        status = "OK" if success else "FAILED"
        print(f"  Iteration {iteration}: {status} ({duration:.1f}s, ${cost})")

        if success and args.phase in ("01b", "01c", "01d", "01e", "02", "04"):
            output_ids: list[str] = []
            if args.phase == "01b":
                output_ids = collect_01b_output_ids(args.worker_id, timestamp, iteration)
            elif args.phase == "01c":
                output_ids = collect_01c_output_ids(args.worker_id, timestamp, iteration)
            else:
                output_ids = validate_output_ids(env_vars.get("OUTPUT_FILE"), args.phase)
            if not output_ids:
                print(
                    f"Worker {args.worker_id}: Invalid or empty output for phase {args.phase}; restoring queue",
                    file=sys.stderr,
                )
                success = False
                if queue_snapshot:
                    save_text(queue_file, queue_snapshot)
            else:
                update_queue_with_ids(queue_file, output_ids)
        if not success:
            print(f"Worker {args.worker_id}: Failed at iteration {iteration}", file=sys.stderr)
            # Restore queue snapshot if Claude may have modified it.
            if queue_snapshot:
                save_text(queue_file, queue_snapshot)

    print(f"Worker {args.worker_id}: Completed {iteration} iterations, total cost: ${total_cost:.4f}")


if __name__ == "__main__":
    main()
