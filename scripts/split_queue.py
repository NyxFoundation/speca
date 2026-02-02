#!/usr/bin/env python3
"""
Split a work queue into multiple worker-specific queues for parallel processing.

Usage:
    python3 scripts/split_queue.py --phase 01b --workers 4
    python3 scripts/split_queue.py --phase 02 --workers 4
    python3 scripts/split_queue.py --phase 03 --workers 4
    python3 scripts/split_queue.py --phase 04 --workers 4
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


# Phase configuration: maps phase to state file location and queue key
PHASE_CONFIG = {
    "01b": {
        "state_file": "outputs/01a_STATE.json",
        "queue_key": "work_queue",
        "output_prefix": "outputs/01b_QUEUE",
    },
    "01c": {
        # Queue is list of subgraph files
        "output_prefix": "outputs/01c_QUEUE",
        "init_from_glob_files": {
            "pattern": "outputs/01b_SUBGRAPHS/spec_*.json",
        },
    },
    "01d": {
        # Queue is list of subgraph files
        "output_prefix": "outputs/01d_QUEUE",
        "init_from_glob_files": {
            "pattern": "outputs/01b_SUBGRAPHS/spec_*.json",
        },
    },
    "01e": {
        # Queue is list of subgraph files
        "output_prefix": "outputs/01e_QUEUE",
        "init_from_glob_files": {
            "pattern": "outputs/01b_SUBGRAPHS/spec_*.json",
        },
    },
    "02": {
        # Queue is list of property descriptors (property_id + source_file)
        "output_prefix": "outputs/02_QUEUE",
        "init_from_glob_items": {
            "pattern": "outputs/01e_PROP_PARTIAL_*.json",
            "item_key": "properties",
            "id_key": "id",
            "id_field": "property_id",
        },
    },
    "03": {
        "state_file": "outputs/03_STATE.json",
        "queue_key": "unprocessed_checklist_ids",
        "output_prefix": "outputs/03_QUEUE",
        # For 03, we need to initialize from 02 checklist partials
        "init_from_glob_items": {
            "pattern": "outputs/02_CHECKLIST_PARTIAL_*.json",
            "item_keys": ["checklist_items", "checklist"],
            "id_key": "id",
            "id_field": "check_id",
        },
    },
    "04": {
        "state_file": "outputs/04_STATE.json",
        "queue_key": "unprocessed_audit_items",
        "output_prefix": "outputs/04_QUEUE",
        # For 04, we need to initialize from 03_AUDITMAP files
        "init_from_glob": {
            "pattern": "outputs/03_AUDITMAP_PARTIAL_*.json",
            "item_key": "audit_items",
            "id_key": "check_id",
        },
    },
}


def load_json(path: str) -> dict[str, Any]:
    """Load JSON file, return empty dict if not exists."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        print(f"Error parsing {path}: {e}", file=sys.stderr)
        return {}


def save_json(path: str, data: dict[str, Any]) -> None:
    """Save data to JSON file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Written: {path}")


def get_items_from_state(config: dict[str, Any]) -> list[Any]:
    """Get the list of items to process from state file."""
    # For file-based queues (01c, 01d, 01e), just get file list
    if "init_from_glob_files" in config:
        items = init_from_glob_files(config["init_from_glob_files"])
        return items
    if "init_from_glob_items" in config:
        items = init_from_glob_items(config["init_from_glob_items"])
        return items

    state_file = config.get("state_file")
    queue_key = config.get("queue_key")

    if state_file and queue_key:
        state = load_json(state_file)
        if state and queue_key in state:
            return state[queue_key]

    # State file doesn't exist or is empty - need to initialize
    if "init_from" in config:
        return init_from_files(config["init_from"])
    elif "init_from_glob" in config:
        items = init_from_glob(config["init_from_glob"])
        # Handle exclusions if specified
        if "exclude_from" in config:
            exclude_ids = set(init_from_glob(config["exclude_from"]))
            items = [i for i in items if i not in exclude_ids]
        return items

    return []


def init_from_glob_files(init_config: dict[str, Any]) -> list[str]:
    """Initialize queue from glob pattern returning file paths (for 01c, 01d, 01e)."""
    import glob

    pattern = init_config["pattern"]
    files = sorted(glob.glob(pattern))
    return files


def init_from_glob_items(init_config: dict[str, Any]) -> list[dict[str, str]]:
    """Initialize queue from glob pattern returning item descriptors (for 02, 03)."""
    import glob

    pattern = init_config["pattern"]
    item_key = init_config.get("item_key")
    item_keys = init_config.get("item_keys")
    id_key = init_config["id_key"]
    id_field = init_config.get("id_field", "property_id")

    items: list[dict[str, str]] = []
    for filepath in sorted(glob.glob(pattern)):
        data = load_json(filepath)
        if item_keys:
            entries = []
            for key in item_keys:
                entries = data.get(key, [])
                if entries:
                    break
        else:
            entries = data.get(item_key, []) if item_key else []
        for entry in entries:
            entry_id = entry.get(id_key) if isinstance(entry, dict) else None
            if entry_id:
                item: dict[str, str] = {id_field: entry_id}
                if isinstance(entry, dict) and "source_file" in entry:
                    item["source_file"] = entry["source_file"]
                items.append(item)

    return items


def init_from_glob(init_config: dict[str, Any]) -> list[str]:
    """Initialize queue from glob pattern (for 03, 04)."""
    import glob

    pattern = init_config["pattern"]
    item_key = init_config["item_key"]
    id_key = init_config["id_key"]
    exclude_patterns = init_config.get("exclude_patterns", [])

    all_ids = []
    for filepath in glob.glob(pattern):
        # Check exclusion patterns
        skip = False
        for exc in exclude_patterns:
            if exc in filepath:
                skip = True
                break
        if skip:
            continue

        data = load_json(filepath)
        items = data.get(item_key, [])
        for item in items:
            if isinstance(item, dict) and id_key in item:
                all_ids.append(item[id_key])
            elif isinstance(item, str):
                all_ids.append(item)

    return all_ids


def split_queue(items: list[Any], workers: int) -> list[list[Any]]:
    """Split items into worker queues using round-robin distribution."""
    queues: list[list[Any]] = [[] for _ in range(workers)]

    for i, item in enumerate(items):
        queues[i % workers].append(item)

    return queues


def main():
    parser = argparse.ArgumentParser(
        description="Split work queue into worker-specific queues for parallel processing"
    )
    parser.add_argument(
        "--phase",
        required=True,
        choices=list(PHASE_CONFIG.keys()),
        help="Phase to split (01b, 01c, 01d, 01e, 02, 03, 04)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of workers (default: 4)",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Output directory (default: outputs)",
    )
    args = parser.parse_args()

    config = PHASE_CONFIG[args.phase]

    print(f"Splitting queue for phase {args.phase} into {args.workers} workers...")

    # Get items to process
    items = get_items_from_state(config)

    if not items:
        print(f"No items to process for phase {args.phase}")
        sys.exit(0)

    print(f"  Total items: {len(items)}")

    # Split into worker queues
    queues = split_queue(items, args.workers)

    # Write worker queue files
    output_prefix = config["output_prefix"]
    for worker_id, queue in enumerate(queues):
        output_path = f"{output_prefix}_{worker_id}.json"
        queue_data = {
            "worker_id": worker_id,
            "phase": args.phase,
            "total_workers": args.workers,
            "items": queue,
            "processed": [],
            "total_items": len(queue),
        }
        save_json(output_path, queue_data)
        print(f"  Worker {worker_id}: {len(queue)} items")

    # Write metadata file for tracking
    metadata_path = f"{output_prefix}_METADATA.json"
    metadata = {
        "phase": args.phase,
        "total_workers": args.workers,
        "total_items": len(items),
        "items_per_worker": [len(q) for q in queues],
        "queue_files": [f"{output_prefix}_{i}.json" for i in range(args.workers)],
    }
    save_json(metadata_path, metadata)

    print(f"Split complete. Run workers with: make {args.phase}-parallel")


if __name__ == "__main__":
    main()
