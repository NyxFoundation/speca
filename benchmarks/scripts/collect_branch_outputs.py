#!/usr/bin/env python3
"""Collect outputs/03_*.json from branches into benchmarks/results/..."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]


def run_git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def resolve_branch(branch: str) -> str:
    candidates = [
        branch,
        f"origin/{branch}",
        f"refs/heads/{branch}",
        f"refs/remotes/origin/{branch}",
    ]
    for ref in candidates:
        try:
            run_git(["show-ref", "--verify", "--quiet", ref])
            return ref
        except subprocess.CalledProcessError:
            continue
    return branch


def list_output_files(branch: str) -> list[str]:
    try:
        output = run_git(["ls-tree", "--name-only", f"{branch}:outputs"])
    except subprocess.CalledProcessError:
        return []
    files = [line.strip() for line in output.splitlines() if line.strip()]
    return [f for f in files if f.startswith("03_") and f.endswith(".json")]


def write_file(branch: str, path: str, dest: Path) -> None:
    content = run_git(["show", f"{branch}:outputs/{path}"])
    dest.write_text(content, encoding="utf-8")


def sanitize_branch(branch: str) -> str:
    return branch.replace("/", "__")


def collect_branch(branch: str, output_root: Path) -> dict:
    ref = resolve_branch(branch)
    sanitized = sanitize_branch(branch)
    dest_dir = output_root / sanitized
    dest_dir.mkdir(parents=True, exist_ok=True)

    files = list_output_files(ref)
    collected = []
    for name in files:
        dest = dest_dir / name
        write_file(ref, name, dest)
        collected.append(name)

    manifest = {
        "branch": branch,
        "ref": ref,
        "sanitized_branch": sanitized,
        "files": collected,
    }
    (dest_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def parse_branches(value: str) -> list[str]:
    parts = [item.strip() for item in value.split(",")]
    return [p for p in parts if p]


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect outputs/03_*.json from branches")
    parser.add_argument("--branches", required=True, help="Comma-separated branch names")
    parser.add_argument(
        "--output-root",
        default=str(ROOT_DIR / "benchmarks" / "results" / "rq1" / "sherlock_ethereum_audit_contest"),
        help="Output root directory",
    )
    args = parser.parse_args()

    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    manifests = []
    for branch in parse_branches(args.branches):
        manifests.append(collect_branch(branch, output_root))

    summary_path = output_root / "collection_summary.json"
    summary_path.write_text(json.dumps({"branches": manifests}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
