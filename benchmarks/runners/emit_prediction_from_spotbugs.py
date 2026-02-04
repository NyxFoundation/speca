#!/usr/bin/env python3
"""Emit benchmark prediction from SpotBugs XML output.

Usage:
  python emit_prediction_from_spotbugs.py --spotbugs-xml spotbugs.xml --output prediction.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.etree import ElementTree as ET


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit prediction from SpotBugs XML report.")
    parser.add_argument("--spotbugs-xml", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.spotbugs_xml.exists():
        raise SystemExit(f"SpotBugs report not found: {args.spotbugs_xml}")

    try:
        tree = ET.parse(args.spotbugs_xml)
        root = tree.getroot()
        findings = len(root.findall(".//BugInstance"))
    except ET.ParseError:
        findings = 0

    prediction = {"predicted_vulnerable": findings > 0, "findings": findings}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(prediction, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
