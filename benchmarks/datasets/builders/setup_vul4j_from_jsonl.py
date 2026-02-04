#!/usr/bin/env python3
"""Prepare a Vul4J paired dataset from a JSONL export.

Expected input format per line (any missing keys will be left empty):
  - id (optional)
  - before (vulnerable code)
  - after (clean code)
  - cve / cwe_id / file_path / language / project (optional)

This script emits paired rows with vul_type and pair_id for evaluation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Vul4J dataset from JSONL.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("benchmarks/data/vul4j/vul4j_export.jsonl"),
        help="Input JSONL export",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/data/vul4j/vul4j_paired.jsonl"),
        help="Output JSONL path",
    )
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        raise SystemExit(f"Input JSONL not found: {args.input}")

    rows_out = []
    pair_count = 0
    with args.input.open("r", encoding="utf-8") as handle:
        for idx, line in enumerate(handle):
            if args.limit and pair_count >= args.limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            before = record.get("before")
            after = record.get("after")
            if not isinstance(before, str) or not before.strip():
                continue
            if not isinstance(after, str) or not after.strip():
                continue
            pair_id = record.get("pair_id") or record.get("id") or f"vul4j:{idx}"
            base = {
                "pair_id": pair_id,
                "cve": record.get("cve"),
                "cwe_id": record.get("cwe_id") or record.get("cwe"),
                "file_path": record.get("file_path") or record.get("file"),
                "language": record.get("language") or "java",
                "project": record.get("project"),
            }
            rows_out.append({**base, "vul_type": "vulnerable", "before": before})
            rows_out.append({**base, "vul_type": "clean", "after": after})
            pair_count += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in rows_out:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Wrote {len(rows_out)} rows ({pair_count} pairs) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
