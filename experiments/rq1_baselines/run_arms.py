#!/usr/bin/env python3
"""RQ1 controlled-baseline runner (issue #102) -- SKELETON.

Runs the three arms (A code-only, B spec-only, C SPECA full) over >=3 independent
runs on the same target, holding model / target commit / phase-04 review constant,
then scores per-arm recall against the #107 population-mapping table.

STATUS: skeleton. It documents the exact wiring and orchestration but is NOT yet
executable end-to-end. Required first (NEITHER done nor tested here):

  1) Register the two variant audit phases in scripts/orchestrator/config.py so
     `run_phase.py --phase <id>` can drive them. PhaseConfig requires
     phase_id/name/description/skill_path/prompt_path/queue_pattern/output_pattern
     (see config.py:44). Stubs (mirror the "03" entry; skill_path/queue_pattern use
     the same neutral-sentinel style as phase 0a):

        "03_codeonly": PhaseConfig(
            phase_id="03_codeonly",
            name="Audit (code-only baseline)",
            description="RQ1 arm A: audit in-scope code units with no spec/properties.",
            skill_path=Path(""),
            prompt_path=Path("experiments/rq1_baselines/prompts/audit_code_only.md"),
            queue_pattern="outputs/03_QUEUE_*.json",
            output_pattern="outputs/03_PARTIAL_*.json",
            depends_on=[],            # no spec/property deps; queue built from scope
            input_patterns=[],        # units come from the arm-A queue builder
            model="sonnet",
            mcp_servers=[],
        ),
        "03_spec_only": PhaseConfig(
            phase_id="03_spec_only",
            name="Audit (spec-only baseline)",
            description="RQ1 arm B: audit against spec/subgraph with no typed properties.",
            skill_path=Path(""),
            prompt_path=Path("experiments/rq1_baselines/prompts/audit_spec_only.md"),
            queue_pattern="outputs/03_QUEUE_*.json",
            output_pattern="outputs/03_PARTIAL_*.json",
            depends_on=["01b"],       # spec + subgraph, no 01e/02c
            input_patterns=["outputs/01b_PARTIAL_*.json"],
            model="sonnet",
            mcp_servers=[],
        ),

  2) A queue builder for arms A/B. Phase 03's queue is normally derived from 02c;
     A/B skip 02c, so units must be built to cover the SAME in-scope code
     population arm C sees (from BUG_BOUNTY_SCOPE in-scope components / 01b
     subgraph regions) WITHOUT property-derived filtering -- see README "queue
     generation and fairness". Without this, arm A recall moves with the code
     population and the causal claim is muddied.

  3) One smoke-test run of each arm on a single target/run to confirm the variant
     prompts emit the {metadata, audit_items[6-field]} schema Phase 04 consumes.

Until (1)-(3) are done, treat any numbers this produces as unverified.
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


def arm_by_id(arm_id: str) -> dict:
    for a in ARMS["arms"]:
        if a["id"] == arm_id or a["id"].startswith(arm_id):
            return a
    raise SystemExit(f"unknown arm: {arm_id}")


def run_arm(arm: dict, run_idx: int, target_workspace: str, model: str, dry_run: bool) -> bool:
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


def score(_arms, _runs) -> None:
    """Compute per-arm recall against the #107 population-mapping table.

    Requires outputs/ findings from each run AND the #107 map (72->19->15). Not
    implemented until the #107 table exists (blocked on findings data)."""
    print("SCORING (not yet runnable -- needs #107 map + run outputs):")
    print("  per arm: recall = |detected AND 15 H/M/L| / 15, with per-severity split")
    print("  property-only-recoverable = (B OR C) MINUS A, listed by finding name")
    print("  report mean +/- range across independent runs; decision rule per README")


def main() -> int:
    ap = argparse.ArgumentParser(description="RQ1 controlled-baseline runner (#102, skeleton)")
    ap.add_argument("--arms", default="A,B,C", help="comma list: A,B,C")
    ap.add_argument("--runs", type=int, default=ARMS["defaults"]["runs"],
                    help="independent runs per arm (>=3 recommended)")
    ap.add_argument("--sherlock-target", dest="sherlock_target",
                    help="target repo workspace path (SPECA_TARGET_WORKSPACE). "
                         "Named to avoid clashing with run_phase.py's --target (=phase).")
    ap.add_argument("--model", default=ARMS["defaults"]["model"])
    ap.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    ap.add_argument("--score", action="store_true", help="score existing runs and exit")
    args = ap.parse_args()

    if args.score:
        score(args.arms.split(","), args.runs)
        return 0

    if not args.sherlock_target:
        ap.error("--sherlock-target is required unless --score")

    ok = True
    for arm_id in args.arms.split(","):
        arm = arm_by_id(arm_id)
        for run_idx in range(args.runs):
            if not run_arm(arm, run_idx, args.sherlock_target, args.model, args.dry_run):
                ok = False
    print("done (dry-run)" if args.dry_run else ("done" if ok else "done WITH ABORTED runs"))
    return 0 if ok or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
