#!/usr/bin/env python3
"""RQ1 controlled-baseline runner (issue #102) -- SKELETON.

Runs the three arms (A code-only, B spec-only, C SPECA full) over >=3 independent
runs on the same target, holding model / target commit / phase-04 review constant,
then scores per-arm recall against the #107 population-mapping table.

STATUS:
  DONE here (self-contained, unit-tested in test_rq1_baselines.py, no compute):
    * the arm A/B queue builder (queue_builder.py), wired into run_arm() so each
      A/B run builds its audit queue before the audit phase, covering the SAME
      in-scope population arm C sees (README "queue generation and fairness").
    * score() — per-arm recall on the 15 H/M/L from Phase-04 outputs against an
      EXTERNAL --gt-map (2-author matches + #107 denominator), mean and min-max
      over runs, and the decisive (B|C)-A property-only-recoverable set.

  REMAINING (needs real compute, gated on the smoke test — do NOT trust numbers
  until done):
    1) Register the two variant phases in scripts/orchestrator/config.py so
       `run_phase.py --phase 03_codeonly|03_spec_only` drives them. Mirror the
       real "03" entry (config.py:339): item_id_field="property_id",
       result_key="audit_items", tools_filter=["Read","Write","Grep","Glob"],
       mcp_servers=[]. NOTE: the live Phase 03 loads work from `input_patterns`
       (02c output) and its `queue_pattern` is "outputs/03_ASYNC_QUEUE_*.json"
       (runner-written per batch), NOT "03_QUEUE_*.json". The variants must point
       `input_patterns` at the queue-builder output and the smoke test must
       confirm Phase03Orchestrator loads those units (add a thin variant loader
       if it does not) — this is exactly why it is smoke-gated and not wired
       blind here. Route in factory.py by `phase_id.startswith("03")`.
    2) One smoke run per arm (1 target, 1 run) confirming the variant prompts emit
       the {metadata, audit_items[6-field]} schema Phase 04 consumes, seen before
       the numbers are trusted (recurring-mistakes rule: verify the real path).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = json.loads((HERE / "arms.json").read_text(encoding="utf-8"))

# Audit-variant phase id -> arm letter, for building the arm A/B queue that Phase
# 03 loads (arms skip 02c, so the queue must be built explicitly; see README /
# queue_builder.py). Kept here so run_arm knows when to build before auditing.
_AUDIT_VARIANT = {"03_codeonly": "A", "03_spec_only": "B"}


def _build_arm_queue(arm_letter: str, out_root: Path, target_workspace: str,
                     shared_scope: str | None = None) -> int:
    """Build the arm A/B audit queue covering the same in-scope population arm C
    sees. Writes into <out_root> directly — `get_output_root()` (paths.py) returns
    SPECA_OUTPUT_DIR itself with NO `outputs/` subdir, and phases write
    BUG_BOUNTY_SCOPE.json / 01b_PARTIAL_*.json there. Raises on an empty queue: a
    silent 0-unit queue would make arm-A recall a spurious 0 — the exact causal
    misread this experiment must avoid (#102 review)."""
    from queue_builder import build_arm_a_units, build_arm_b_units, write_queue

    ws = Path(target_workspace)
    if arm_letter == "A":
        # Arm A runs no scope-extraction phase (0a); the shared scope must be
        # passed in (--bug-bounty-scope) so every arm audits the SAME scope.
        scope = None
        if shared_scope:
            scope = _first_json([Path(shared_scope)])
        scope = scope or _first_json([out_root / "BUG_BOUNTY_SCOPE.json", ws / "BUG_BOUNTY_SCOPE.json"])
        ti = _first_json([out_root / "TARGET_INFO.json", ws / "TARGET_INFO.json"])
        units = build_arm_a_units(scope or {}, ti)
        arm_id = "A_code_only"
    else:  # B — 01b partials produced by the arm's own 01b phase (runs first)
        parts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out_root.glob("01b_PARTIAL_*.json"))]
        units = build_arm_b_units(parts)
        arm_id = "B_spec_only"
    if not units:
        raise SystemExit(
            f"[{arm_id}] built 0 audit units — refusing to run a fair-queue arm on "
            f"an empty queue. For arm A pass --bug-bounty-scope <shared BUG_BOUNTY_SCOPE.json>; "
            f"for arm B confirm 01b produced 01b_PARTIAL_*.json in {out_root}."
        )
    write_queue(units, out_root / "03_ASYNC_QUEUE_W0B0.json", arm_id)
    return len(units)


def _first_json(paths: list[Path]) -> dict | None:
    for p in paths:
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None


def arm_by_id(arm_id: str) -> dict:
    for a in ARMS["arms"]:
        if a["id"] == arm_id or a["id"].startswith(arm_id):
            return a
    raise SystemExit(f"unknown arm: {arm_id}")


def run_arm(arm: dict, run_idx: int, target_workspace: str, model: str, dry_run: bool,
            shared_scope: str | None = None) -> bool:
    """Run one arm as one independent run. Each (arm, run) writes to a disjoint
    output root so arms never thrash the same venv/outputs, and pins SPECA_RUN_ID
    (see CLAUDE.md) for determinism. Returns True on success, False if any phase
    exits non-zero (the run is aborted at that point and recorded)."""
    out_root = HERE / "runs" / arm["id"] / f"run{run_idx}"
    out_root.mkdir(parents=True, exist_ok=True)
    run_id = f"rq1-{arm['id']}-r{run_idx}"
    child_env = {
        **os.environ,
        # Real env contract (see scripts/run_phase.py / phase0_runner.py):
        "SPECA_RUN_ID": run_id,
        "SPECA_OUTPUT_DIR": str(out_root),
        "SPECA_TARGET_WORKSPACE": target_workspace,
    }
    for phase in arm["phases"]:
        # Arms A/B skip 02c, so build their audit queue right before the audit
        # phase (arm B needs 01b to have run first — the phase list orders it so).
        if phase in _AUDIT_VARIANT and not dry_run:
            # An empty/misbuilt queue aborts THIS (arm, run) only — same
            # ABORTED.txt-and-continue contract as a failed phase below, not a
            # process-wide SystemExit that would take down other arms/runs (#156).
            try:
                n = _build_arm_queue(_AUDIT_VARIANT[phase], out_root, target_workspace, shared_scope)
            except SystemExit as exc:
                (out_root / "ABORTED.txt").write_text(f"queue build for {phase}: {exc}\n", encoding="utf-8")
                print(f"[{arm['id']} run{run_idx}] ABORT: queue build for {phase}: {exc}")
                return False
            print(f"[{arm['id']} run{run_idx}] built {phase} queue: {n} units")
        # model is a run_phase.py FLAG (--model), not an env var.
        cmd = [
            sys.executable, "scripts/run_phase.py",
            "--phase", phase,
            "--model", model,
            "--output-dir", str(out_root),
            "--json",
        ]
        print(f"[{arm['id']} run{run_idx}] phase {phase}: {' '.join(cmd)}")
        if dry_run:
            continue
        rc = subprocess.run(cmd, env=child_env).returncode
        if rc != 0:
            # Abort this (arm, run) and record it; do not run later phases on a
            # broken upstream (would silently score a partial pipeline).
            (out_root / "ABORTED.txt").write_text(
                f"phase {phase} exited {rc}\n", encoding="utf-8"
            )
            print(f"[{arm['id']} run{run_idx}] ABORT: phase {phase} exited {rc}")
            return False
    return True


_CONFIRMED_VERDICTS = {"CONFIRMED_VULNERABILITY", "CONFIRMED_POTENTIAL", "Confirmed"}


def _confirmed_finding_ids(run_root: Path) -> set[str]:
    """Finding ids (property_id / check_id) confirmed by Phase 04 in one run."""
    ids: set[str] = set()
    # Phase 04 writes 04_PARTIAL_*.json into run_root itself — get_output_root()
    # (paths.py) returns SPECA_OUTPUT_DIR with NO `outputs/` subdir. Same fix as
    # _build_arm_queue; verified against the real layout in the test below (#156).
    for fp in sorted(run_root.glob("04_PARTIAL_*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in data.get("reviewed_items", []):
            if str(item.get("review_verdict", "")).strip() in _CONFIRMED_VERDICTS:
                fid = item.get("property_id") or item.get("check_id") or ""
                if fid:
                    ids.add(str(fid))
    return ids


def _recovered_gt(finding_ids: set[str], finding_to_gt: dict[str, str]) -> set[str]:
    """Ground-truth ids recovered = gt ids any confirmed finding mapped to."""
    return {finding_to_gt[f] for f in finding_ids if f in finding_to_gt}


def score(arms: list[str], runs: int, gt_map_path: str | None) -> int:
    """Per-arm recall on the 15 H/M/L, using an EXTERNAL match map.

    gt_map (JSON, from the 2-author matching + #107 denominator; parameterized):
      {"ground_truth": [{"id": "H1", "severity": "High"}, ...],   # the 15 in-scope H/M/L
       "finding_to_gt": {"<property_id/check_id>": "<gt id>", ...}}
    The map is the single denominator source (README / #107); this function only
    aggregates 04 outputs against it and never invents a match. Reports per-arm
    recall as mean and min-max over the independent runs, and the
    property-only-recoverable set (B|C) MINUS A."""
    if not gt_map_path:
        print("SCORING needs --gt-map (the 2-author match map + #107 denominator).", file=sys.stderr)
        print("  Format: {ground_truth:[{id,severity}], finding_to_gt:{finding_id:gt_id}}", file=sys.stderr)
        return 2
    gt = json.loads(Path(gt_map_path).read_text(encoding="utf-8"))
    all_gt = [g["id"] for g in gt.get("ground_truth", [])]
    sev = {g["id"]: g.get("severity", "?") for g in gt.get("ground_truth", [])}
    f2g = gt.get("finding_to_gt", {})
    denom = len(all_gt)
    if denom == 0:
        print("gt_map has no ground_truth; cannot score.", file=sys.stderr)
        return 2

    # per arm: recovered-gt set per run + union across runs
    recovered_union: dict[str, set[str]] = {}
    for arm_id in arms:
        arm = arm_by_id(arm_id)
        per_run_recall: list[float] = []
        union: set[str] = set()
        for run_idx in range(runs):
            run_root = HERE / "runs" / arm["id"] / f"run{run_idx}"
            rec = _recovered_gt(_confirmed_finding_ids(run_root), f2g)
            union |= rec
            per_run_recall.append(round(len(rec) / denom, 4))
        recovered_union[arm["id"]] = union
        by_sev = {s: sum(1 for g in union if sev.get(g) == s) for s in ("High", "Medium", "Low")}
        mean = round(sum(per_run_recall) / len(per_run_recall), 4) if per_run_recall else None
        rng = (min(per_run_recall), max(per_run_recall)) if per_run_recall else None
        print(f"[{arm['id']}] recall mean={mean} min-max={rng} over {runs} run(s) | "
              f"union recovered {len(union)}/{denom} (H/M/L={by_sev['High']}/{by_sev['Medium']}/{by_sev['Low']})")

    # property-only-recoverable = (B|C) MINUS A, listed by gt id (the decisive set)
    a = recovered_union.get(arm_by_id("A")["id"], set())
    b = recovered_union.get(arm_by_id("B")["id"], set()) if any(x.startswith("B") for x in arms) else set()
    c = recovered_union.get(arm_by_id("C")["id"], set()) if any(x.startswith("C") for x in arms) else set()
    property_only = sorted((b | c) - a, key=lambda g: (sev.get(g, "?"), g))
    print(f"property-only-recoverable (B|C) MINUS A = {property_only} "
          f"({len(property_only)} of {denom}; the A(1) causal set — named explicitly)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="RQ1 controlled-baseline runner (#102, skeleton)")
    ap.add_argument("--arms", default="A,B,C", help="comma list: A,B,C")
    ap.add_argument("--runs", type=int, default=ARMS["defaults"]["runs"],
                    help="independent runs per arm (>=3 recommended)")
    ap.add_argument("--sherlock-target", dest="sherlock_target",
                    help="target repo workspace path (SPECA_TARGET_WORKSPACE). "
                         "Named to avoid clashing with run_phase.py's --target (=phase).")
    ap.add_argument("--model", default=ARMS["defaults"]["model"])
    ap.add_argument("--bug-bounty-scope", dest="bug_bounty_scope",
                    help="shared BUG_BOUNTY_SCOPE.json for arm A (arm A runs no scope-"
                         "extraction phase; all arms must audit the SAME scope — "
                         "hold_constant: bug_bounty_scope).")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    ap.add_argument("--score", action="store_true", help="score existing runs and exit")
    ap.add_argument("--gt-map", dest="gt_map",
                    help="JSON match map for scoring (2-author matches + #107 denominator); "
                         "see score() docstring")
    args = ap.parse_args()

    if args.score:
        return score(args.arms.split(","), args.runs, args.gt_map)

    if not args.sherlock_target:
        ap.error("--sherlock-target is required unless --score")

    ok = True
    for arm_id in args.arms.split(","):
        arm = arm_by_id(arm_id)
        for run_idx in range(args.runs):
            if not run_arm(arm, run_idx, args.sherlock_target, args.model, args.dry_run,
                           args.bug_bounty_scope):
                ok = False
    print("done (dry-run)" if args.dry_run else ("done" if ok else "done WITH ABORTED runs"))
    return 0 if ok or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
