#!/usr/bin/env python3
"""Arm A/B audit-queue builder for the RQ1 controlled baselines (issue #102).

Arms A (code-only) and B (spec-only) skip Phase 02c, so their audit units must be
built explicitly. The causal-validity rule (README "queue generation and
fairness"): the arm-A/B queue must cover the SAME in-scope code population arm C
sees, with NO property-derived filtering — otherwise arm-A recall moves with the
code surface, not with the presence/absence of properties, and the A(1) claim is
muddied.

- Arm A: units = the in-scope components enumerated from BUG_BOUNTY_SCOPE.json
  (and TARGET_INFO.json when present). No spec, no property.
- Arm B: units = the Phase 01b subgraph regions (spec excerpt + mermaid), no typed
  property. Each unit carries its informal spec obligation as provenance so #103
  can tell arm-B findings from arm-C typed-property findings.

Everything is parameterized (scope path, 01b glob, target-info, output path, arm)
so the harness does not block on the pending #122 seed-count / #107 denominator
decisions. Output is the queue the Phase 03 orchestrator loads
(`queue_pattern = outputs/03_ASYNC_QUEUE_*.json`). Each unit carries the Phase 03
id field `property_id` (the real `item_id_field`) AND `check_id`, both set to a
surrogate `armA-<NNN>` / `armB-<NNN>`, so it is consumed like an arm-C item.

Scope schema (verified vs phase0_runner.py / real BUG_BOUNTY_SCOPE.json):
`in_scope_assets` is a flat list[str] of repos/paths/addresses (NOT a nested
`in_scope.components` dict); `in_scope_contracts` is a list of dicts. Both are
enumerated (older shapes tolerated as a fallback).
"""
from __future__ import annotations

import argparse
import glob as glob_mod
import json
import sys
from pathlib import Path
from typing import Any


def _sid(arm_letter: str, n: int) -> str:
    """Surrogate finding id, e.g. armA-001 (1-based, zero-padded to 3)."""
    return f"arm{arm_letter}-{n:03d}"


def _in_scope_units(scope: dict[str, Any]) -> list[tuple[str, str]]:
    """(label, code_path) per in-scope asset from a real BUG_BOUNTY_SCOPE.json.

    The file that phase0_runner.py generates (and 01e consumes) has a top-level
    `in_scope_assets: list[str]` (repos / file paths / addresses) plus
    `in_scope_contracts: list[dict]`. We enumerate those; a plain legacy shape
    (`in_scope_components` / `components` as str or dict) is tolerated as a
    fallback so an older scope file still yields units instead of silently zero.
    """
    out: list[tuple[str, str]] = []
    assets = scope.get("in_scope_assets")
    if isinstance(assets, list):
        for a in assets:
            if isinstance(a, str) and a.strip():
                out.append((a.strip(), a.strip()))
            elif isinstance(a, dict):
                p = a.get("path") or a.get("name") or a.get("asset")
                if p:
                    out.append((str(p), str(p)))
    for c in scope.get("in_scope_contracts") or []:
        if isinstance(c, dict):
            label = c.get("name") or c.get("address")
            if label:
                out.append((str(label), str(c.get("address") or label)))
    if not out:  # legacy / fallback shapes
        legacy = scope.get("in_scope_components") or scope.get("components") or []
        if isinstance(legacy, dict):
            legacy = legacy.get("components") or legacy.get("targets") or []
        for c in legacy:
            if isinstance(c, str) and c.strip():
                out.append((c.strip(), c.strip()))
            elif isinstance(c, dict):
                p = c.get("path") or c.get("file") or c.get("name") or c.get("symbol")
                if p:
                    out.append((str(p), str(p)))
    return out


def build_arm_a_units(scope: dict[str, Any], target_info: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Arm A units: one per in-scope asset (no spec/property signal). Covers the
    same in-scope population arm C sees (from BUG_BOUNTY_SCOPE / TARGET_INFO)."""
    pairs = _in_scope_units(scope)
    if target_info:
        pairs = pairs + _in_scope_units(target_info)
    seen: set[str] = set()
    units: list[dict[str, Any]] = []
    for label, code_path in pairs:
        if label in seen:
            continue
        seen.add(label)
        cid = _sid("A", len(units) + 1)
        units.append({
            "check_id": cid,
            "property_id": cid,           # surrogate (README): arms A/B have no property
            "arm": "A_code_only",
            "code_path": code_path,
            "asset": label,
        })
    return units


def build_arm_b_units(subgraph_partials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Arm B units: one per Phase 01b subgraph region (spec + subgraph, no property)."""
    units: list[dict[str, Any]] = []
    for part in subgraph_partials:
        for spec in part.get("specs", []):
            src = spec.get("source_url", "")
            for sg in spec.get("sub_graphs", []):
                cid = _sid("B", len(units) + 1)
                invariants = sg.get("invariants", []) or []
                units.append({
                    "check_id": cid,
                    "property_id": cid,
                    "arm": "B_spec_only",
                    "subgraph_id": sg.get("id", ""),
                    "subgraph_name": sg.get("name", ""),
                    "source_url": src,
                    "mermaid_file": sg.get("mermaid_file", ""),
                    # Informal spec obligations (NOT typed properties): provenance so
                    # #103 can separate arm-B findings from arm-C typed-property ones.
                    "obligation_hint": invariants,
                })
    return units


def write_queue(units: list[dict[str, Any]], out_path: Path, arm_id: str) -> Path:
    """Write the queue in the shape the Phase 03 orchestrator loads."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"metadata": {"arm": arm_id, "unit_count": len(units), "source": "rq1_baselines.queue_builder"},
               "items": units}
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def _load_json(p: str) -> Any:
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser(description="RQ1 arm A/B audit-queue builder (#102)")
    ap.add_argument("--arm", required=True, choices=["A", "B"], help="A=code-only, B=spec-only")
    ap.add_argument("--scope", help="BUG_BOUNTY_SCOPE.json (arm A)")
    ap.add_argument("--target-info", help="TARGET_INFO.json (arm A, optional)")
    ap.add_argument("--b01-glob", help="glob for 01b partials (arm B), e.g. outputs/01b_PARTIAL_*.json")
    ap.add_argument("--out", required=True, help="output queue path, e.g. outputs/03_QUEUE_W0B0.json")
    args = ap.parse_args()

    if args.arm == "A":
        if not args.scope:
            ap.error("arm A requires --scope")
        scope = _load_json(args.scope)
        ti = _load_json(args.target_info) if args.target_info else None
        units = build_arm_a_units(scope, ti)
        arm_id = "A_code_only"
    else:
        if not args.b01_glob:
            ap.error("arm B requires --b01-glob")
        parts = [_load_json(p) for p in sorted(glob_mod.glob(args.b01_glob))]
        units = build_arm_b_units(parts)
        arm_id = "B_spec_only"

    if not units:
        print("WARNING: 0 units built — check the scope/01b inputs (a fair queue must be non-empty).", file=sys.stderr)
    out = write_queue(units, Path(args.out), arm_id)
    print(f"wrote {out}: {len(units)} units (arm {arm_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
