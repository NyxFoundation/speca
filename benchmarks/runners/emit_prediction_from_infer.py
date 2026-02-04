#!/usr/bin/env python3
"""Emit benchmark prediction from Infer output.

Usage:
  python emit_prediction_from_infer.py --infer-json /path/to/report.json --output /path/to/prediction.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit prediction from Infer JSON report.")
    parser.add_argument("--infer-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.infer_json.exists():
        raise SystemExit(f"Infer report not found: {args.infer_json}")

    try:
        data = json.loads(args.infer_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = []

    findings = 0
    if isinstance(data, list):
        findings = len(data)
    elif isinstance(data, dict):
        issues = data.get("issues") or data.get("results") or []
        if isinstance(issues, list):
            findings = len(issues)

    prediction = {"predicted_vulnerable": findings > 0, "findings": findings}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(prediction, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
