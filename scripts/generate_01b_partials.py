#!/usr/bin/env python3
"""Generate 01b_PARTIAL JSON files from existing .mmd subgraph files.

Scans outputs/graphs/batch_w*_<timestamp>/ directories, extracts metadata
from .mmd YAML frontmatter, and writes Phase01bPartial-compliant JSON files
that the pipeline (Phase 01e) can consume.

Usage:
    python scripts/generate_01b_partials.py [--timestamp 1774522356] [--dry-run]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Resolve project root (one level up from scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
GRAPHS_DIR = OUTPUTS_DIR / "graphs"

# Source URL mapping from 01a_STATE.json — keyed by contract/doc name
# We build this dynamically from the 01a state file.


def load_source_url_map() -> dict[str, str]:
    """Load 01a_STATE.json and build a mapping from filename stem to source URL."""
    state_path = OUTPUTS_DIR / "01a_STATE.json"
    if not state_path.exists():
        print(f"Warning: {state_path} not found, source_url will be empty", file=sys.stderr)
        return {}

    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)

    url_map: dict[str, str] = {}
    for spec in state.get("found_specs", []):
        url = spec.get("url", "")
        title = spec.get("title", "")
        if url:
            # Extract the stem from the URL path (e.g. "BaseAuction" from ".../BaseAuction.sol")
            stem = Path(url.rstrip("/")).stem
            url_map[stem] = url
            # Also store the title keyed by stem
            url_map[f"_title_{stem}"] = title
    return url_map


def parse_mmd_frontmatter(mmd_path: Path) -> dict[str, str]:
    """Extract YAML frontmatter from an .mmd file.

    Returns dict with 'title' and any other frontmatter keys.
    """
    content = mmd_path.read_text(encoding="utf-8")
    frontmatter: dict[str, str] = {}

    # Match YAML frontmatter between --- delimiters
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if match:
        for line in match.group(1).strip().splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                frontmatter[key.strip()] = value.strip().strip('"').strip("'")

    return frontmatter


def extract_invariants(mmd_path: Path) -> list[str]:
    """Extract invariant lines from 'note right of' blocks in an .mmd file."""
    content = mmd_path.read_text(encoding="utf-8")
    invariants: list[str] = []

    # Find all "note right of" blocks
    in_note = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("note right of"):
            in_note = True
            continue
        if in_note:
            if stripped == "end note":
                in_note = False
                continue
            if stripped.startswith("INV-"):
                invariants.append(stripped)

    return invariants


def build_subgraph_entry(mmd_path: Path, contract_name: str) -> dict:
    """Build a SubGraph dict from an .mmd file."""
    frontmatter = parse_mmd_frontmatter(mmd_path)
    invariants = extract_invariants(mmd_path)

    # Extract SG-XXX id and function name from filename like "SG-001_constructor.mmd"
    stem = mmd_path.stem  # e.g. "SG-001_constructor"
    match = re.match(r"(SG-\d+)_(.*)", stem)
    if match:
        sg_id = match.group(1)
        func_name = match.group(2)
    else:
        sg_id = stem
        func_name = stem

    # mermaid_file is relative path from the graphs dir (e.g. "BaseAuction/SG-001_constructor.mmd")
    mermaid_file = f"{contract_name}/{mmd_path.name}"

    return {
        "id": sg_id,
        "name": func_name,
        "mermaid_file": mermaid_file,
        "program_graph": {"Q": [], "q_init": "", "q_final": "", "Act": [], "E": []},
        "invariants": invariants,
    }


def generate_partials(timestamp: int, dry_run: bool = False) -> list[Path]:
    """Generate 01b_PARTIAL files for all batch directories matching the timestamp."""
    url_map = load_source_url_map()
    batch_pattern = f"batch_*_{timestamp}"
    batch_dirs = sorted(GRAPHS_DIR.glob(batch_pattern))

    if not batch_dirs:
        print(f"No batch directories found matching {GRAPHS_DIR / batch_pattern}")
        sys.exit(1)

    print(f"Found {len(batch_dirs)} batch directories for timestamp {timestamp}")

    created_files: list[Path] = []

    for batch_dir in batch_dirs:
        # Parse worker and batch index from dir name: batch_w0b0_1774522356
        dir_match = re.match(r"batch_w(\d+)b(\d+)_(\d+)", batch_dir.name)
        if not dir_match:
            print(f"  Skipping unrecognized dir: {batch_dir.name}", file=sys.stderr)
            continue

        worker_id = int(dir_match.group(1))
        batch_index = int(dir_match.group(2))

        # Each batch dir may contain one or more contract subdirectories
        contract_dirs = [d for d in sorted(batch_dir.iterdir()) if d.is_dir()]

        if not contract_dirs:
            print(f"  Skipping empty batch: {batch_dir.name}")
            continue

        specs: list[dict] = []
        processed_ids: list[str] = []

        for contract_dir in contract_dirs:
            contract_name = contract_dir.name
            mmd_files = sorted(contract_dir.glob("*.mmd"))

            if not mmd_files:
                print(f"    No .mmd files in {contract_name}, skipping")
                continue

            # Look up source URL from 01a state
            source_url = url_map.get(contract_name, "")
            title = url_map.get(f"_title_{contract_name}", f"{contract_name}")

            sub_graphs = []
            for mmd_path in mmd_files:
                sg = build_subgraph_entry(mmd_path, contract_name)
                sub_graphs.append(sg)

            spec_entry = {
                "source_url": source_url,
                "title": title,
                "sub_graphs": sub_graphs,
            }
            specs.append(spec_entry)
            if source_url:
                processed_ids.append(source_url)

            print(f"    {contract_name}: {len(sub_graphs)} subgraphs, url={source_url[:60] if source_url else '(none)'}...")

        if not specs:
            print(f"  No specs generated for {batch_dir.name}, skipping")
            continue

        # Build the Phase01bPartial-compliant output
        total_subgraphs = sum(len(s["sub_graphs"]) for s in specs)
        output_data = {
            "specs": specs,
            "metadata": {
                "phase": "01b",
                "worker_id": worker_id,
                "batch_index": batch_index,
                "item_count": len(specs),
                "timestamp": timestamp,
                "processed_ids": processed_ids,
            },
        }

        output_filename = f"01b_PARTIAL_W{worker_id}B{batch_index}_{timestamp}.json"
        output_path = OUTPUTS_DIR / output_filename

        if dry_run:
            print(f"  [DRY RUN] Would write: {output_path.name}")
            print(f"            {len(specs)} spec(s), {total_subgraphs} subgraph(s)")
            print(json.dumps(output_data, indent=2)[:500])
            print("  ...")
        else:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2)
            print(f"  Wrote: {output_path.name} ({len(specs)} spec(s), {total_subgraphs} subgraph(s))")
            created_files.append(output_path)

    return created_files


def validate_outputs(files: list[Path]) -> bool:
    """Validate generated files against the Phase01bPartial schema."""
    # Import via the orchestrator package (requires pydantic in environment)
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.orchestrator.schemas import Phase01bPartial
    Phase01bPartial.model_rebuild()

    all_ok = True
    for filepath in files:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        try:
            partial = Phase01bPartial.model_validate(data)
            total_sg = sum(len(s.sub_graphs) for s in partial.specs)
            print(f"  VALID: {filepath.name} — {len(partial.specs)} spec(s), {total_sg} subgraph(s)")
        except Exception as e:
            print(f"  INVALID: {filepath.name} — {e}", file=sys.stderr)
            all_ok = False

    return all_ok


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate 01b_PARTIAL JSON files from .mmd subgraph data")
    parser.add_argument("--timestamp", type=int, default=1774522356,
                        help="Batch timestamp to process (default: 1774522356)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be generated without writing files")
    parser.add_argument("--skip-validation", action="store_true",
                        help="Skip Pydantic schema validation after generation")
    args = parser.parse_args()

    print(f"Generating 01b PARTIAL files for timestamp {args.timestamp}")
    print(f"Graphs dir: {GRAPHS_DIR}")
    print()

    files = generate_partials(args.timestamp, dry_run=args.dry_run)

    if files and not args.dry_run and not args.skip_validation:
        print()
        print("Validating generated files against Phase01bPartial schema...")
        if validate_outputs(files):
            print()
            print(f"Done. {len(files)} file(s) created and validated.")
        else:
            print()
            print("Some files failed validation — check warnings above.", file=sys.stderr)
            sys.exit(1)
    elif args.dry_run:
        print()
        print("[DRY RUN] No files written.")


if __name__ == "__main__":
    main()
