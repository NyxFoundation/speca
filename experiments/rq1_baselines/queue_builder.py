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
(`queue_pattern = outputs/03_QUEUE_*.json`); each unit's id field is `check_id`
(the Phase 03 `item_id_field`), a surrogate `armA-<NNN>` / `armB-<NNN>`.
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


def _scope_components(scope: dict[str, Any]) -> list[dict[str, Any]]:
    """In-scope components from a BUG_BOUNTY_SCOPE.json, tolerant of shape drift.

    Accepts `in_scope` as a list of component dicts, or `in_scope.components`, or
    a top-level `components` list. A component is any dict; we keep the fields that
    locate code (name/path/file/symbol/region) and ignore the rest.
    """
    in_scope = scope.get("in_scope", scope.get("scope", {}))
    if isinstance(in_scope, dict):
        comps = in_scope.get("components") or in_scope.get("targets") or []
    elif isinstance(in_scope, list):
        comps = in_scope
    else:
        comps = []
    if not comps:
        comps = scope.get("components", [])
    return [c for c in comps if isinstance(c, dict)]


def build_arm_a_units(scope: dict[str, Any], target_info: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Arm A units: one per in-scope code component, no spec/property signal."""
    comps = _scope_components(scope)
    # TARGET_INFO may enumerate additional in-scope components; union by (path/name).
    if target_info:
        comps = comps + [c for c in _scope_components(target_info) if isinstance(c, dict)]
    seen: set[str] = set()
    units: list[dict[str, Any]] = []
    for c in comps:
        key = str(c.get("path") or c.get("file") or c.get("name") or c.get("symbol") or json.dumps(c, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        cid = _sid("A", len(units) + 1)
        units.append({
            "check_id": cid,
            "property_id": cid,           # surrogate (README): arms A/B have no property
            "arm": "A_code_only",
            "code_path": c.get("path") or c.get("file") or c.get("symbol") or c.get("name", ""),
            "component": {k: c.get(k) for k in ("name", "path", "file", "symbol", "region", "language") if c.get(k) is not None},
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
