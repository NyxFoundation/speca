#!/usr/bin/env python3
"""
Merge partial results from parallel workers into a single output file.

Usage:
    python3 scripts/merge_results.py --phase 01b --output outputs/01_SPEC.json
    python3 scripts/merge_results.py --phase 03 --output outputs/03_AUDITMAP_MERGED.json
    python3 scripts/merge_results.py --phase 04 --output outputs/04_REVIEW_MERGED.json
"""

import argparse
import glob
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# Phase configuration for merging
MERGE_CONFIG = {
    "01b": {
        "partial_pattern": "outputs/01b_SUBGRAPHS/spec_*.json",
        "output_structure": {
            "type": "integration",
            "nodes_key": "sub_graph.nodes",
            "edges_key": "sub_graph.edges",
        },
    },
    "03": {
        "partial_pattern": "outputs/03_AUDITMAP_PARTIAL_*.json",
        "merge_keys": ["audit_items", "verified_items"],
    },
    "04": {
        "partial_pattern": "outputs/04_REVIEW_PARTIAL_*.json",
        "merge_keys": ["reviewed_items", "verified_items"],
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
    print(f"Written: {path}")


def get_nested(data: dict, key_path: str) -> Any:
    """Get nested value using dot notation."""
    keys = key_path.split(".")
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key, [])
        else:
            return []
    return result


def merge_01b(pattern: str, output_path: str) -> None:
    """Merge 01b subgraphs into integrated specification.

    Supports both old format (single sub_graph) and new format (sub_graphs array).
    """
    files = sorted(glob.glob(pattern))

    if not files:
        print(f"No files found matching {pattern}")
        sys.exit(1)

    print(f"Merging {len(files)} subgraph files...")

    all_nodes = []
    all_edges = []
    all_external_entities = []
    all_ambiguities = []
    all_assumptions = []
    source_urls = []
    all_aspects = set()
    total_subgraphs = 0

    seen_node_ids = set()
    seen_edge_ids = set()
    seen_entity_ids = set()

    for filepath in files:
        data = load_json(filepath)
        source_urls.append(data.get("source_url", filepath))

        sub_graphs = data.get("sub_graphs", [])

        for sub_graph in sub_graphs:
            total_subgraphs += 1

            # Track aspects
            aspect = sub_graph.get("aspect")
            if aspect:
                all_aspects.add(aspect)

            # Merge nodes (deduplicate by ID)
            for node in sub_graph.get("nodes", []):
                node_id = node.get("id")
                if node_id and node_id not in seen_node_ids:
                    all_nodes.append(node)
                    seen_node_ids.add(node_id)

            # Merge edges (deduplicate by ID)
            for edge in sub_graph.get("edges", []):
                edge_id = edge.get("id")
                if edge_id and edge_id not in seen_edge_ids:
                    all_edges.append(edge)
                    seen_edge_ids.add(edge_id)

            # Merge external entities (deduplicate by ID)
            for entity in sub_graph.get("external_entities", []):
                entity_id = entity.get("id")
                if entity_id and entity_id not in seen_entity_ids:
                    all_external_entities.append(entity)
                    seen_entity_ids.add(entity_id)

        # Merge ambiguities and assumptions (keep all)
        all_ambiguities.extend(data.get("ambiguities", []))
        all_assumptions.extend(data.get("implicit_assumptions", []))

    # Build merged output
    merged = {
        "metadata": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source_count": len(files),
            "total_subgraphs": total_subgraphs,
            "aspects_covered": sorted(all_aspects),
            "source_urls": source_urls,
        },
        "integrated_graph": {
            "id": "INTEGRATED-SPEC",
            "title": "Integrated System Specification",
            "nodes": all_nodes,
            "edges": all_edges,
            "external_entities": all_external_entities,
        },
        "ambiguities": all_ambiguities,
        "implicit_assumptions": all_assumptions,
        "statistics": {
            "total_nodes": len(all_nodes),
            "total_edges": len(all_edges),
            "total_external_entities": len(all_external_entities),
            "total_ambiguities": len(all_ambiguities),
            "total_assumptions": len(all_assumptions),
            "total_subgraphs": total_subgraphs,
            "aspects_count": len(all_aspects),
        },
    }

    save_json(output_path, merged)
    print(f"Merged {len(all_nodes)} nodes, {len(all_edges)} edges from {total_subgraphs} subgraphs ({len(files)} files)")


def merge_simple(pattern: str, merge_key: str, output_path: str) -> None:
    """Merge files with a simple array key."""
    files = sorted(glob.glob(pattern))

    if not files:
        print(f"No files found matching {pattern}")
        sys.exit(1)

    print(f"Merging {len(files)} partial files...")

    all_items = []
    seen_ids = set()

    for filepath in files:
        data = load_json(filepath)
        items = data.get(merge_key, [])

        for item in items:
            item_id = item.get("id")
            if item_id and item_id not in seen_ids:
                all_items.append(item)
                seen_ids.add(item_id)

    merged = {
        "metadata": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source_count": len(files),
        },
        merge_key: all_items,
        "statistics": {
            f"total_{merge_key}": len(all_items),
        },
    }

    save_json(output_path, merged)
    print(f"Merged {len(all_items)} items from {len(files)} files")


def merge_multi_key(pattern: str, merge_keys: list[str], output_path: str) -> None:
    """Merge files with multiple array keys (03, 04)."""
    files = sorted(glob.glob(pattern))

    if not files:
        print(f"No files found matching {pattern}")
        sys.exit(1)

    print(f"Merging {len(files)} partial files...")

    all_items: dict[str, list] = {key: [] for key in merge_keys}
    seen_ids: dict[str, set] = {key: set() for key in merge_keys}

    for filepath in files:
        data = load_json(filepath)

        for key in merge_keys:
            items = data.get(key, [])
            for item in items:
                # Try different ID fields
                item_id = item.get("check_id") or item.get("id") or item.get("item_id")
                if item_id and item_id not in seen_ids[key]:
                    all_items[key].append(item)
                    seen_ids[key].add(item_id)

    merged = {
        "metadata": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source_count": len(files),
        },
        **all_items,
        "statistics": {
            f"total_{key}": len(items) for key, items in all_items.items()
        },
    }

    save_json(output_path, merged)
    for key, items in all_items.items():
        print(f"  {key}: {len(items)} items")


def main():
    parser = argparse.ArgumentParser(
        description="Merge partial results from parallel workers"
    )
    parser.add_argument(
        "--phase",
        required=True,
        choices=list(MERGE_CONFIG.keys()),
        help="Phase to merge (01b, 03, 04)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file path",
    )
    parser.add_argument(
        "--pattern",
        help="Override partial file pattern",
    )
    args = parser.parse_args()

    config = MERGE_CONFIG[args.phase]
    pattern = args.pattern or config["partial_pattern"]

    print(f"Merging phase {args.phase} results...")
    print(f"  Pattern: {pattern}")
    print(f"  Output: {args.output}")

    if args.phase == "01b":
        merge_01b(pattern, args.output)
    elif "merge_key" in config:
        merge_simple(pattern, config["merge_key"], args.output)
    elif "merge_keys" in config:
        merge_multi_key(pattern, config["merge_keys"], args.output)
    else:
        print(f"Unknown merge strategy for phase {args.phase}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
