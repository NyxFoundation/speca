#!/usr/bin/env python3
"""
Filter specifications by target layer (consensus/execution).

Usage:
    python3 scripts/filter_specs_by_layer.py --input outputs/01a_STATE.json \
        --output outputs/01a_STATE_FILTERED.json --target-layer consensus

Layer Mapping:
    - consensus: "consensus", "consensus+networking", "consensus+execution"
    - execution: "execution", "consensus+execution"
"""

import argparse
import json
from pathlib import Path
from typing import Any


def filter_specs(
    specs: list[dict[str, Any]], target_layer: str
) -> list[dict[str, Any]]:
    """
    Filter specs by target layer.

    Args:
        specs: List of spec dictionaries from 01a_STATE.json
        target_layer: "consensus" or "execution"

    Returns:
        Filtered list of specs matching the target layer
    """
    filtered = []
    layer_map = {
        "consensus": {"consensus", "consensus+networking", "consensus+execution"},
        "execution": {"execution", "consensus+execution"},
    }

    valid_layers = layer_map.get(target_layer)
    if not valid_layers:
        raise ValueError(f"Invalid target_layer: {target_layer}")

    for spec in specs:
        spec_layer = spec.get("layer", "")
        if spec_layer in valid_layers:
            filtered.append(spec)

    return filtered


def main():
    parser = argparse.ArgumentParser(
        description="Filter specifications by target layer"
    )
    parser.add_argument(
        "--input", required=True, help="Input 01a_STATE.json file path"
    )
    parser.add_argument(
        "--output", required=True, help="Output filtered JSON file path"
    )
    parser.add_argument(
        "--target-layer",
        required=True,
        choices=["consensus", "execution"],
        help="Target layer: consensus or execution",
    )

    args = parser.parse_args()

    # Read input
    input_path = Path(args.input)
    with input_path.open("r") as f:
        data = json.load(f)

    # Filter specs
    original_count = len(data.get("found_specs", []))
    data["found_specs"] = filter_specs(data.get("found_specs", []), args.target_layer)
    filtered_count = len(data["found_specs"])

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        json.dump(data, f, indent=2)

    print(f"Filtered specs by layer: {args.target_layer}")
    print(f"Original specs: {original_count}")
    print(f"Filtered specs: {filtered_count}")
    print(f"Removed: {original_count - filtered_count}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
