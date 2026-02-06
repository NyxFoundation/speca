#!/usr/bin/env python3
"""Build RQ1 run metadata from collection summary + environment."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build RQ1 metadata JSON")
    parser.add_argument("--collection", required=True, help="Path to collection_summary.json")
    parser.add_argument("--output", required=True, help="Output metadata JSON path")
    parser.add_argument("--ai-version", default="", help="AI/LLM version string")
    parser.add_argument("--ai-name", default="claude", help="AI/LLM name")
    parser.add_argument("--phase-id", default="03", help="Phase ID to attach timing for")
    args = parser.parse_args()

    collection = load_json(Path(args.collection))
    branches = collection.get("branches", [])

    targets = []
    for entry in branches:
        target_info = entry.get("target_info") or {}
        phase_logs = entry.get("phase_log_timing") or {}
        target = {
            "branch": entry.get("branch"),
            "ref": entry.get("ref"),
            "commit": target_info.get("target_commit") or entry.get("commit"),
            "commit_short": target_info.get("target_commit_short") or entry.get("commit_short"),
            "target_repo": target_info.get("target_repo"),
            "target_ref_type": target_info.get("target_ref_type"),
            "target_ref_label": target_info.get("target_ref_label"),
            f"phase_{args.phase_id}": phase_logs or {},
            "files_collected": len(entry.get("files", [])),
        }
        targets.append(target)

    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ai": {
            "name": args.ai_name,
            "version": args.ai_version,
        },
        "targets": targets,
        "collection": {
            "path": args.collection,
            "output_globs": collection.get("output_globs", []),
            "logs_dir": collection.get("logs_dir"),
            "log_phase": collection.get("log_phase"),
        },
        "notes": {
            "phase_timing_source": "outputs/logs",
            "phase_timing_caveat": "Timing is estimated from phase log timestamps when available.",
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
