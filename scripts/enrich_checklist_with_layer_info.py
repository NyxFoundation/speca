#!/usr/bin/env python3
"""
Enrich checklist items with specification layer information for layer mismatch detection.

This script adds a `spec_layer` field to each checklist item by matching it back to
the original specification from 01a_STATE.json.

Usage:
    python3 scripts/enrich_checklist_with_layer_info.py \
        --specs outputs/01a_STATE.json \
        --checklist outputs/02_PARTIAL_*.json \
        --output outputs/02_ENRICHED/

This allows Phase 02c to detect layer mismatches early and mark them as `layer_mismatch`
instead of spending resources on futile code searches.
"""

import argparse
import json
from pathlib import Path
from typing import Any


def load_specs(specs_path: Path) -> dict[str, dict[str, Any]]:
    """
    Load specifications and create a mapping by URL.

    Returns:
        Dict mapping spec URL to spec metadata (including layer)
    """
    with specs_path.open("r") as f:
        data = json.load(f)

    specs_by_url = {}
    for spec in data.get("found_specs", []):
        url = spec.get("url", "")
        if url:
            specs_by_url[url] = {
                "layer": spec.get("layer", "unknown"),
                "title": spec.get("title", ""),
                "status": spec.get("status", ""),
            }

    return specs_by_url


def extract_spec_url_from_notes(notes: str) -> str | None:
    """
    Extract specification URL from checklist item notes.

    Notes format examples:
        "Source: PROP-W0B17-1, Trust Boundary: tb-010. EIP-7934 specific defense."
        "Derived from EIP-7594 (PeerDAS) specification..."

    Returns:
        Extracted URL or None
    """
    # Simple heuristic: extract EIP number and construct URL
    import re

    # Look for EIP-XXXX pattern
    match = re.search(r"EIP-(\d+)", notes, re.IGNORECASE)
    if match:
        eip_num = match.group(1)
        return f"https://github.com/ethereum/EIPs/blob/master/EIPS/eip-{eip_num}.md"

    return None


def enrich_checklist_item(
    item: dict[str, Any], specs_by_url: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """
    Add spec_layer field to checklist item.

    Strategy:
        1. Try to extract spec URL from notes field
        2. Match against specs_by_url mapping
        3. Add spec_layer field (or "unknown" if not found)
    """
    notes = item.get("notes", "")
    spec_url = extract_spec_url_from_notes(notes)

    if spec_url and spec_url in specs_by_url:
        spec_info = specs_by_url[spec_url]
        item["spec_layer"] = spec_info["layer"]
        item["spec_url"] = spec_url
    else:
        item["spec_layer"] = "unknown"
        item["spec_url"] = None

    return item


def process_checklist_file(
    checklist_path: Path,
    specs_by_url: dict[str, dict[str, Any]],
    output_dir: Path,
) -> tuple[int, int]:
    """
    Process a single checklist file and enrich with layer info.

    Returns:
        Tuple of (total_items, enriched_items)
    """
    with checklist_path.open("r") as f:
        data = json.load(f)

    checklist_key = "checklist" if "checklist" in data else "checklist_with_code"
    items = data.get(checklist_key, [])

    enriched_count = 0
    for item in items:
        original_layer = item.get("spec_layer")
        enrich_checklist_item(item, specs_by_url)
        if item.get("spec_layer") != "unknown":
            enriched_count += 1

    # Write enriched checklist
    output_path = output_dir / checklist_path.name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        json.dump(data, f, indent=2)

    return len(items), enriched_count


def main():
    parser = argparse.ArgumentParser(
        description="Enrich checklist items with spec layer info"
    )
    parser.add_argument(
        "--specs", required=True, type=Path, help="Path to 01a_STATE.json"
    )
    parser.add_argument(
        "--checklist",
        required=True,
        help="Glob pattern for checklist files (e.g., 'outputs/02_PARTIAL_*.json')",
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="Output directory for enriched files"
    )

    args = parser.parse_args()

    # Load specs
    print(f"Loading specifications from {args.specs}...")
    specs_by_url = load_specs(args.specs)
    print(f"Loaded {len(specs_by_url)} specifications")

    # Process checklist files
    import glob

    checklist_files = glob.glob(args.checklist)
    print(f"Found {len(checklist_files)} checklist files matching pattern")

    total_items = 0
    total_enriched = 0

    for checklist_path in checklist_files:
        checklist_path = Path(checklist_path)
        items, enriched = process_checklist_file(
            checklist_path, specs_by_url, args.output
        )
        total_items += items
        total_enriched += enriched
        print(
            f"  {checklist_path.name}: {enriched}/{items} items enriched "
            f"({enriched/items*100:.1f}%)"
        )

    print(f"\nTotal: {total_enriched}/{total_items} items enriched")
    print(f"Output directory: {args.output}")


if __name__ == "__main__":
    main()
